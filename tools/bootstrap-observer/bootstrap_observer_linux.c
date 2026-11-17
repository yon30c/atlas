#define _GNU_SOURCE

#include "bootstrap_observer_linux.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include <termios.h>

static int read_bounded_file(const char *path, unsigned char *buffer,
                             size_t maximum, size_t *length) {
    int fd;
    size_t used = 0;

    fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }

    while (used < maximum + 1U) {
        ssize_t count = read(fd, buffer + used, maximum + 1U - used);

        if (count < 0) {
            if (errno == EINTR) {
                continue;
            }
            {
                int saved = errno;
                (void)close(fd);
                errno = saved;
            }
            return -1;
        }
        if (count == 0) {
            break;
        }
        used += (size_t)count;
    }

    {
        int saved = errno;
        (void)close(fd);
        errno = saved;
    }

    if (used > maximum) {
        errno = EOVERFLOW;
        return -1;
    }
    if (used == 0) {
        errno = EIO;
        return -1;
    }

    *length = used;
    return 0;
}

static int make_proc_path(char *path, size_t capacity, pid_t pid,
                          const char *leaf) {
    int count = snprintf(path, capacity, "/proc/%ld/%s", (long)pid, leaf);

    if (count < 0 || (size_t)count >= capacity) {
        errno = ENAMETOOLONG;
        return -1;
    }
    return 0;
}

static bool read_process_snapshot(pid_t pid, bv_status *status,
                                  bv_stat *stat_value,
                                  bv_parse_result *status_result,
                                  bv_parse_result *stat_result) {
    unsigned char status_buffer[ATLAS_PROC_STATUS_MAX + 1U];
    unsigned char stat_buffer[ATLAS_PROC_STAT_MAX + 1U];
    char path[64];
    size_t length;

    if (make_proc_path(path, sizeof(path), pid, "status") != 0 ||
        read_bounded_file(path, status_buffer, ATLAS_PROC_STATUS_MAX,
                          &length) != 0) {
        *status_result = bo_classify_read(0U, ATLAS_PROC_STATUS_MAX, errno);
        return false;
    }
    *status_result = bv_parse_status(status_buffer, length, status);
    if (*status_result != BV_OK) {
        return false;
    }

    if (make_proc_path(path, sizeof(path), pid, "stat") != 0 ||
        read_bounded_file(path, stat_buffer, ATLAS_PROC_STAT_MAX,
                          &length) != 0) {
        *stat_result = bo_classify_read(0U, ATLAS_PROC_STAT_MAX, errno);
        return false;
    }
    *stat_result = bv_parse_stat(stat_buffer, length, (int32_t)pid,
                                 stat_value);
    return *stat_result == BV_OK;
}

bv_parse_result bo_classify_read(size_t bytes_read, size_t maximum,
                                 int read_error) {
    if (read_error == EOVERFLOW || bytes_read > maximum) {
        return BV_TOO_LARGE;
    }
    if (read_error != 0 || bytes_read == 0U) {
        return BV_TRUNCATED;
    }
    return BV_OK;
}

bv_pidfd_state bo_pidfd_state_from_poll(int poll_result, int revents) {
    if (poll_result == 0) {
        return BV_PIDFD_OPEN_UNSIGNALED;
    }
    if (poll_result > 0 && (revents & POLLIN) != 0) {
        return BV_PIDFD_SIGNALED;
    }
    return BV_PIDFD_NOT_REQUESTED;
}

bool bo_session_matches(int32_t parent_sid, int32_t observer_sid) {
    return parent_sid > 0 && observer_sid > 0 && parent_sid == observer_sid;
}

bool bo_parent_samples_match(const bv_status *status_a,
                             const bv_stat *stat_a,
                             const bv_status *status_b,
                             const bv_stat *stat_b) {
    if (status_a == NULL || stat_a == NULL ||
        status_b == NULL || stat_b == NULL) {
        return false;
    }
    return status_a->ppid == status_b->ppid &&
           memcmp(status_a->uid, status_b->uid, sizeof(status_a->uid)) == 0 &&
           memcmp(status_a->gid, status_b->gid, sizeof(status_a->gid)) == 0 &&
           stat_a->pid == stat_b->pid && stat_a->state == stat_b->state &&
           stat_a->ppid == stat_b->ppid && stat_a->pgrp == stat_b->pgrp &&
           stat_a->session == stat_b->session &&
           stat_a->tty_nr == stat_b->tty_nr &&
           stat_a->tpgid == stat_b->tpgid &&
           stat_a->starttime == stat_b->starttime;
}

bool bo_executable_samples_match(uint64_t device_a, uint64_t inode_a,
                                 uint32_t mode_a, uint32_t uid_a,
                                 uint32_t gid_a, uint64_t device_b,
                                 uint64_t inode_b, uint32_t mode_b,
                                 uint32_t uid_b, uint32_t gid_b) {
    return device_a == device_b && inode_a == inode_b &&
           mode_a == mode_b && uid_a == uid_b && gid_a == gid_b;
}

static bv_pidfd_state inspect_pidfd(int fd, int *error_number) {
    struct pollfd item;
    int result;

    item.fd = fd;
    item.events = POLLIN;
    item.revents = 0;
    result = poll(&item, 1, 0);
    if (result < 0 && error_number != NULL) {
        *error_number = errno;
    } else if (result > 0 && (item.revents & POLLIN) == 0 &&
               error_number != NULL) {
        *error_number = EIO;
    }
    return bo_pidfd_state_from_poll(result, item.revents);
}

static int open_pidfd(pid_t pid) {
#ifdef SYS_pidfd_open
    return (int)syscall(SYS_pidfd_open, pid, 0U);
#else
    (void)pid;
    errno = ENOSYS;
    return -1;
#endif
}

typedef struct {
    bool available;
    uint64_t device;
    uint64_t inode;
    uint32_t mode;
    uint32_t uid;
    uint32_t gid;
} exe_observation;

static exe_observation inspect_executable(pid_t pid, char *target,
                                         size_t target_capacity) {
    exe_observation result = {0};
    char path[64];
    struct stat metadata;
    ssize_t length;
    int fd;

    if (make_proc_path(path, sizeof(path), pid, "exe") != 0) {
        return result;
    }
    fd = open(path, O_PATH | O_CLOEXEC);
    if (fd < 0) {
        return result;
    }
    if (fstat(fd, &metadata) != 0) {
        (void)close(fd);
        return result;
    }
    (void)close(fd);

    result.available = true;
    result.device = (uint64_t)metadata.st_dev;
    result.inode = (uint64_t)metadata.st_ino;
    result.mode = (uint32_t)metadata.st_mode;
    result.uid = (uint32_t)metadata.st_uid;
    result.gid = (uint32_t)metadata.st_gid;

    if (target != NULL && target_capacity > 1U) {
        length = readlink(path, target, target_capacity - 1U);
        if (length >= 0) {
            target[(size_t)length] = '\0';
        } else {
            target[0] = '\0';
        }
    }
    return result;
}

static bool same_executable(const exe_observation *a,
                            const exe_observation *b) {
    return a->available && b->available &&
           bo_executable_samples_match(
               a->device, a->inode, a->mode, a->uid, a->gid,
               b->device, b->inode, b->mode, b->uid, b->gid);
}

typedef struct {
    bool available;
    int32_t terminal_sid;
    int32_t process_sid;
    int32_t process_pgrp;
    int32_t foreground_pgrp;
    int error_number;
} tty_observation;

static tty_observation inspect_tty(void) {
    tty_observation result = {0};
    int fd;
    pid_t terminal_sid;
    pid_t foreground;

    fd = open("/dev/tty", O_RDONLY | O_CLOEXEC | O_NOCTTY);
    if (fd < 0) {
        result.error_number = errno;
        return result;
    }

    terminal_sid = tcgetsid(fd);
    if (terminal_sid < 0) {
        result.error_number = errno;
        (void)close(fd);
        return result;
    }
    foreground = tcgetpgrp(fd);
    if (foreground < 0) {
        result.error_number = errno;
        (void)close(fd);
        return result;
    }

    result.process_sid = (int32_t)getsid(0);
    result.process_pgrp = (int32_t)getpgrp();
    result.terminal_sid = (int32_t)terminal_sid;
    result.foreground_pgrp = (int32_t)foreground;
    result.available = true;
    (void)close(fd);
    return result;
}

int bo_collect(bo_report *report) {
    bv_fixture_policy policy = {0};
    bv_observation observation = {0};
    exe_observation exe_first;
    exe_observation exe_second;
    tty_observation tty;
    int pidfd = -1;
    pid_t self_pid;
    pid_t parent_pid;
    bool first_ok;
    bool second_ok;
    int original_errno = 0;

    if (report == NULL) {
        errno = EINVAL;
        return -1;
    }
    memset(report, 0, sizeof(*report));
    report->result = BV_OBSERVATION_INCOMPLETE;
    report->pidfd_state = BV_PIDFD_NOT_REQUESTED;
    report->status_parse_first = BV_TRUNCATED;
    report->status_parse_second = BV_TRUNCATED;
    report->stat_parse_first = BV_TRUNCATED;
    report->stat_parse_second = BV_TRUNCATED;

    self_pid = getpid();
    parent_pid = getppid();
    if (self_pid <= 0 || parent_pid <= 0 || self_pid == parent_pid) {
        errno = ESRCH;
        return -1;
    }
    report->self_pid = self_pid;
    report->parent_pid = parent_pid;
    report->process_sid = (int32_t)getsid(0);
    report->process_pgrp = (int32_t)getpgrp();

    pidfd = open_pidfd(parent_pid);
    if (pidfd >= 0) {
        report->pidfd_state = inspect_pidfd(pidfd, &report->pidfd_errno);
    } else {
        report->pidfd_errno = errno;
    }

    {
        unsigned char buffer[ATLAS_PROC_STAT_MAX + 1U];
        char path[64];
        size_t length;
        bv_parse_result parsed;

        if (make_proc_path(path, sizeof(path), self_pid, "stat") == 0 &&
            read_bounded_file(path, buffer, ATLAS_PROC_STAT_MAX, &length) == 0) {
            parsed = bv_parse_stat(buffer, length, (int32_t)self_pid,
                                   &report->self_stat);
            report->have_self_stat = parsed == BV_OK;
        }
    }

    first_ok = read_process_snapshot(parent_pid,
                                     &report->parent_status_first,
                                     &report->parent_stat_first,
                                     &report->status_parse_first,
                                     &report->stat_parse_first);
    report->have_parent_first = first_ok;

    exe_first = inspect_executable(parent_pid, report->exe_target,
                                   sizeof(report->exe_target));
    report->exe_first_available = exe_first.available;

    second_ok = read_process_snapshot(parent_pid,
                                      &report->parent_status_second,
                                      &report->parent_stat_second,
                                      &report->status_parse_second,
                                      &report->stat_parse_second);
    report->have_parent_second = second_ok;

    exe_second = inspect_executable(parent_pid, NULL, 0U);
    report->exe_second_available = exe_second.available;
    report->exe_stable = same_executable(&exe_first, &exe_second);
    if (exe_first.available) {
        report->exe_device = exe_first.device;
        report->exe_inode = exe_first.inode;
        report->exe_mode = exe_first.mode;
        report->exe_uid = exe_first.uid;
        report->exe_gid = exe_first.gid;
    }

    if (first_ok && second_ok) {
        report->parent_stable =
            bo_parent_samples_match(&report->parent_status_first,
                                    &report->parent_stat_first,
                                    &report->parent_status_second,
                                    &report->parent_stat_second);
    }

    tty = inspect_tty();
    report->tty_available = tty.available;
    report->tty_errno = tty.error_number;
    if (tty.available) {
        report->terminal_sid = tty.terminal_sid;
        report->foreground_pgrp = tty.foreground_pgrp;
    }

    observation.has_requested_pid = true;
    observation.requested_pid = (int32_t)parent_pid;
    observation.has_helper_pid = true;
    observation.helper_pid = (int32_t)self_pid;
    observation.has_helper_parent_pid = true;
    observation.helper_parent_pid = (int32_t)getppid();

    if (first_ok) {
        observation.has_parent_status = true;
        observation.parent_status = report->parent_status_first;
        observation.has_parent_stat = true;
        observation.parent_stat = report->parent_stat_first;
        observation.has_parent_starttime_first = true;
        observation.parent_starttime_first =
            report->parent_stat_first.starttime;
    }
    if (second_ok) {
        observation.has_parent_starttime_second = true;
        observation.parent_starttime_second =
            report->parent_stat_second.starttime;
    }

    observation.parent_pidfd = report->pidfd_state;
    if (tty.available) {
        observation.has_tty_relations = true;
        observation.terminal_sid = tty.terminal_sid;
        observation.process_sid = tty.process_sid;
        observation.process_pgrp = tty.process_pgrp;
        observation.foreground_pgrp = tty.foreground_pgrp;
    }

    report->result = bv_evaluate(&observation, &policy);

    if (first_ok && second_ok && !report->parent_stable) {
        report->result = BV_OBSERVATION_INCONSISTENT;
    }
    if (report->exe_first_available && report->exe_second_available &&
        !report->exe_stable) {
        report->result = BV_OBSERVATION_INCONSISTENT;
    }
    if (getppid() != parent_pid) {
        report->result = BV_OBSERVATION_INCONSISTENT;
    }
    if (report->have_self_stat &&
        (report->self_stat.session != report->process_sid ||
         report->self_stat.pgrp != report->process_pgrp ||
         (tty.available &&
          report->self_stat.tpgid != report->foreground_pgrp))) {
        report->result = BV_OBSERVATION_INCONSISTENT;
    }
    if (first_ok &&
        !bo_session_matches(report->parent_stat_first.session,
                            report->process_sid)) {
        report->result = BV_OBSERVATION_INCONSISTENT;
    }
    if (!report->have_self_stat || !first_ok || !second_ok ||
        !report->exe_first_available || !report->exe_second_available ||
        !report->tty_available ||
        report->pidfd_state == BV_PIDFD_NOT_REQUESTED) {
        if (report->result != BV_OBSERVATION_INCONSISTENT) {
            report->result = BV_OBSERVATION_INCOMPLETE;
        }
    }

    if (pidfd >= 0) {
        int final_pidfd_error = 0;
        bv_pidfd_state final_state =
            inspect_pidfd(pidfd, &final_pidfd_error);
        if (final_state == BV_PIDFD_SIGNALED) {
            report->pidfd_state = final_state;
            report->result = BV_OBSERVATION_INCONSISTENT;
        } else if (final_state != BV_PIDFD_OPEN_UNSIGNALED) {
            report->pidfd_state = BV_PIDFD_NOT_REQUESTED;
            if (report->pidfd_errno == 0) {
                report->pidfd_errno = final_pidfd_error;
            }
            if (report->result != BV_OBSERVATION_INCONSISTENT) {
                report->result = BV_OBSERVATION_INCOMPLETE;
            }
        }
        if (close(pidfd) != 0) {
            original_errno = errno;
        }
    }

    if (original_errno != 0 && report->result == BV_OBSERVATION_CONSISTENT) {
        report->result = BV_OBSERVATION_INCOMPLETE;
    }
    return 0;
}

bool bo_parse_hold_ms(const char *value, unsigned *milliseconds) {
    unsigned parsed = 0;

    if (value == NULL || milliseconds == NULL || *value == '\0') {
        return false;
    }
    for (const unsigned char *p = (const unsigned char *)value; *p; p++) {
        unsigned digit;

        if (*p < '0' || *p > '9') {
            return false;
        }
        digit = (unsigned)(*p - '0');
        if (parsed > (30000U - digit) / 10U) {
            return false;
        }
        parsed = parsed * 10U + digit;
    }
    if (parsed < 1000U || parsed > 30000U) {
        return false;
    }
    *milliseconds = parsed;
    return true;
}

int bo_run_hold(bo_report *report, unsigned milliseconds) {
    tty_observation baseline;

    if (report == NULL || milliseconds < 1000U || milliseconds > 30000U) {
        errno = EINVAL;
        return -1;
    }
    baseline = inspect_tty();
    if (!baseline.available) {
        if (report->result != BV_OBSERVATION_INCONSISTENT) {
            report->result = BV_OBSERVATION_INCOMPLETE;
        }
        return 0;
    }
    if (!report->tty_available ||
        baseline.terminal_sid != report->terminal_sid ||
        baseline.process_sid != report->process_sid ||
        baseline.process_pgrp != report->process_pgrp ||
        baseline.foreground_pgrp != report->foreground_pgrp) {
        report->tty_changed = true;
        report->result = BV_OBSERVATION_INCONSISTENT;
        return 0;
    }

    {
        unsigned samples = (milliseconds + 99U) / 100U;
        const struct timespec interval = {0, 100000000L};

        for (unsigned i = 0; i < samples; i++) {
            struct timespec remaining = interval;
            tty_observation current;

            while (nanosleep(&remaining, &remaining) != 0) {
                if (errno == EINTR) {
                    continue;
                }
                return -1;
            }
            current = inspect_tty();
            if (!current.available ||
                current.terminal_sid != baseline.terminal_sid ||
                current.process_sid != baseline.process_sid ||
                current.process_pgrp != baseline.process_pgrp ||
                current.foreground_pgrp != baseline.foreground_pgrp) {
                report->tty_changed = true;
                report->result = BV_OBSERVATION_INCONSISTENT;
                return 0;
            }
        }
    }
    return 0;
}

static const char *result_name(bv_observation_result result) {
    switch (result) {
    case BV_OBSERVATION_CONSISTENT:
        return "OBSERVATION_CONSISTENT";
    case BV_OBSERVATION_INCONSISTENT:
        return "OBSERVATION_INCONSISTENT";
    case BV_OBSERVATION_INCOMPLETE:
    default:
        return "OBSERVATION_INCOMPLETE";
    }
}

static const char *pidfd_name(bv_pidfd_state state) {
    switch (state) {
    case BV_PIDFD_OPEN_UNSIGNALED:
        return "OPEN_UNSIGNALED";
    case BV_PIDFD_SIGNALED:
        return "SIGNALED";
    case BV_PIDFD_ERROR:
        return "ERROR";
    case BV_PIDFD_NOT_REQUESTED:
    default:
        return "UNAVAILABLE";
    }
}

static const char *parse_name(bv_parse_result result) {
    switch (result) {
    case BV_OK: return "OK";
    case BV_INVALID: return "INVALID";
    case BV_TRUNCATED: return "TRUNCATED_OR_UNREADABLE";
    case BV_MISSING: return "MISSING";
    case BV_DUPLICATE: return "DUPLICATE";
    case BV_RANGE: return "RANGE";
    case BV_TOO_LARGE: return "TOO_LARGE";
    default: return "UNKNOWN";
    }
}

void bo_print_report(FILE *stream, const bo_report *report) {
    if (stream == NULL || report == NULL) {
        return;
    }

    fprintf(stream, "observer_pid=%ld\n", (long)report->self_pid);
    fprintf(stream, "observed_parent_pid=%ld\n", (long)report->parent_pid);
    fprintf(stream, "result=%s\n", result_name(report->result));
    fprintf(stream, "observer_sid=%" PRId32 "\n", report->process_sid);
    fprintf(stream, "observer_pgrp=%" PRId32 "\n", report->process_pgrp);
    if (report->have_self_stat) {
        fprintf(stream, "observer_starttime=%" PRIu64 "\n",
                report->self_stat.starttime);
        fprintf(stream, "observer_tty_nr=%" PRId64 "\n",
                report->self_stat.tty_nr);
        fprintf(stream, "observer_tpgid=%" PRId32 "\n",
                report->self_stat.tpgid);
    } else {
        fprintf(stream, "observer_stat=UNAVAILABLE\n");
    }
    fprintf(stream, "pidfd=%s\n", pidfd_name(report->pidfd_state));
    if (report->pidfd_errno != 0) {
        fprintf(stream, "pidfd_errno=%d (%s)\n", report->pidfd_errno,
                strerror(report->pidfd_errno));
    }
    fprintf(stream, "parent_first_sample=%s\n",
            report->have_parent_first ? "OK" : "UNAVAILABLE");
    fprintf(stream, "parent_second_sample=%s\n",
            report->have_parent_second ? "OK" : "UNAVAILABLE");
    fprintf(stream, "parent_status_parse_first=%s\n",
            parse_name(report->status_parse_first));
    fprintf(stream, "parent_stat_parse_first=%s\n",
            parse_name(report->stat_parse_first));
    fprintf(stream, "parent_status_parse_second=%s\n",
            parse_name(report->status_parse_second));
    fprintf(stream, "parent_stat_parse_second=%s\n",
            parse_name(report->stat_parse_second));
    fprintf(stream, "parent_stable=%s\n",
            report->parent_stable ? "yes" : "no");

    if (report->have_parent_first) {
        const bv_status *status = &report->parent_status_first;
        const bv_stat *stat_value = &report->parent_stat_first;

        fprintf(stream, "parent_ppid=%" PRId32 "\n", status->ppid);
        fprintf(stream, "parent_uid=%" PRIu32 "/%" PRIu32 "/%" PRIu32
                        "/%" PRIu32 "\n",
                status->uid[0], status->uid[1], status->uid[2], status->uid[3]);
        fprintf(stream, "parent_gid=%" PRIu32 "/%" PRIu32 "/%" PRIu32
                        "/%" PRIu32 "\n",
                status->gid[0], status->gid[1], status->gid[2], status->gid[3]);
        fprintf(stream, "parent_state=%c\n", stat_value->state);
        fprintf(stream, "parent_starttime=%" PRIu64 "\n",
                stat_value->starttime);
        fprintf(stream, "parent_sid=%" PRId32 "\n", stat_value->session);
        fprintf(stream, "parent_pgrp=%" PRId32 "\n", stat_value->pgrp);
        fprintf(stream, "parent_tty_nr=%" PRId64 "\n", stat_value->tty_nr);
        fprintf(stream, "parent_tpgid=%" PRId32 "\n", stat_value->tpgid);
    }

    fprintf(stream, "parent_exe_first=%s\n",
            report->exe_first_available ? "OPEN" : "UNAVAILABLE");
    fprintf(stream, "parent_exe_second=%s\n",
            report->exe_second_available ? "OPEN" : "UNAVAILABLE");
    fprintf(stream, "parent_exe_stable=%s\n",
            report->exe_stable ? "yes" : "no");
    if (report->exe_first_available) {
        fprintf(stream, "parent_exe_device=%" PRIu64 "\n",
                report->exe_device);
        fprintf(stream, "parent_exe_inode=%" PRIu64 "\n",
                report->exe_inode);
        fprintf(stream, "parent_exe_mode=%#o\n", report->exe_mode);
        fprintf(stream, "parent_exe_uid=%" PRIu32 "\n", report->exe_uid);
        fprintf(stream, "parent_exe_gid=%" PRIu32 "\n", report->exe_gid);
        if (report->exe_target[0] != '\0') {
            fprintf(stream, "parent_exe_target=%s\n", report->exe_target);
        }
    }

    if (report->tty_available) {
        fprintf(stream, "tty=AVAILABLE\n");
        fprintf(stream, "terminal_sid=%" PRId32 "\n", report->terminal_sid);
        fprintf(stream, "foreground_pgrp=%" PRId32 "\n",
                report->foreground_pgrp);
    } else {
        fprintf(stream, "tty=UNAVAILABLE\n");
        if (report->tty_errno != 0) {
            fprintf(stream, "tty_errno=%d (%s)\n", report->tty_errno,
                    strerror(report->tty_errno));
        }
    }
    fprintf(stream, "tty_changed_during_hold=%s\n",
            report->tty_changed ? "yes" : "no");
    fprintf(stream, "AUTHORIZATION=NOT_PROVIDED\n");
}
