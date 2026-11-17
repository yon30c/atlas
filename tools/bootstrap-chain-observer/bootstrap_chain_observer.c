#define _GNU_SOURCE

#include "bootstrap_chain_observer.h"

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

static int read_bounded(const char *path, unsigned char *buffer,
                        size_t maximum, size_t *length) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    size_t used = 0U;

    if (fd < 0) {
        return -1;
    }
    while (used <= maximum) {
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
        if (used > maximum) {
            (void)close(fd);
            errno = EOVERFLOW;
            return -1;
        }
    }
    if (close(fd) != 0) {
        return -1;
    }
    *length = used;
    return 0;
}

static int proc_path(char *buffer, size_t capacity, pid_t pid,
                     const char *leaf) {
    int count = snprintf(buffer, capacity, "/proc/%ld/%s", (long)pid, leaf);
    if (count < 0 || (size_t)count >= capacity) {
        errno = ENAMETOOLONG;
        return -1;
    }
    return 0;
}

static int pidfd_open_local(pid_t pid) {
#ifdef SYS_pidfd_open
    return (int)syscall(SYS_pidfd_open, pid, 0U);
#else
    (void)pid;
    errno = ENOSYS;
    return -1;
#endif
}

static bool pidfd_alive(int fd) {
    struct pollfd item;
    int result;

    item.fd = fd;
    item.events = POLLIN;
    item.revents = 0;
    result = poll(&item, 1, 0);
    return result == 0;
}

static bool read_executable(pid_t pid, aco_node *node) {
    char path[64];
    struct stat metadata;
    ssize_t length;
    int fd;

    if (proc_path(path, sizeof(path), pid, "exe") != 0) {
        return false;
    }
    fd = open(path, O_PATH | O_CLOEXEC);
    if (fd < 0) {
        return false;
    }
    if (fstat(fd, &metadata) != 0) {
        (void)close(fd);
        return false;
    }
    (void)close(fd);
    length = readlink(path, node->exe_target,
                      sizeof(node->exe_target) - 1U);
    if (length < 0 || (size_t)length >= sizeof(node->exe_target) - 1U) {
        return false;
    }
    node->exe_target[(size_t)length] = '\0';
    node->exe_device = (uint64_t)metadata.st_dev;
    node->exe_inode = (uint64_t)metadata.st_ino;
    node->exe_mode = (uint32_t)metadata.st_mode;
    node->exe_uid = (uint32_t)metadata.st_uid;
    node->exe_gid = (uint32_t)metadata.st_gid;
    node->have_exe = true;
    return true;
}

static bool capture_node(pid_t pid, aco_node *node) {
    unsigned char buffer[ATLAS_PROC_STATUS_MAX + 1U];
    char path[64];
    size_t length;

    memset(node, 0, sizeof(*node));
    node->pid = pid;

    if (proc_path(path, sizeof(path), pid, "status") != 0 ||
        read_bounded(path, buffer, ATLAS_PROC_STATUS_MAX, &length) != 0 ||
        bv_parse_status(buffer, length, &node->status) != BV_OK) {
        return false;
    }
    node->have_status = true;

    if (proc_path(path, sizeof(path), pid, "stat") != 0 ||
        read_bounded(path, buffer, ATLAS_PROC_STAT_MAX, &length) != 0 ||
        bv_parse_stat(buffer, length, (int32_t)pid, &node->stat) != BV_OK) {
        return false;
    }
    node->have_stat = true;

    if (node->status.ppid != node->stat.ppid ||
        !read_executable(pid, node)) {
        return false;
    }
    return true;
}

static bool tty_snapshot(int fd, int32_t *sid, int32_t *foreground) {
    pid_t terminal_sid;
    pid_t foreground_pgrp;

    terminal_sid = tcgetsid(fd);
    if (terminal_sid < 0) {
        return false;
    }
    foreground_pgrp = tcgetpgrp(fd);
    if (foreground_pgrp < 0) {
        return false;
    }
    *sid = (int32_t)terminal_sid;
    *foreground = (int32_t)foreground_pgrp;
    return true;
}

bool aco_is_sudo_candidate(const aco_node *node) {
    const char *base;
    const char *slash;

    if (node == NULL || !node->have_exe ||
        !S_ISREG((mode_t)node->exe_mode) ||
        node->exe_uid != 0U || node->exe_gid != 0U ||
        (node->exe_mode & S_ISUID) == 0U ||
        (node->exe_mode & (S_IWGRP | S_IWOTH)) != 0U) {
        return false;
    }

    slash = strrchr(node->exe_target, '/');
    base = slash == NULL ? node->exe_target : slash + 1;
    return strcmp(base, "sudo") == 0;
}

bool aco_node_equal(const aco_node *left, const aco_node *right) {
    if (left == NULL || right == NULL ||
        left->pid != right->pid ||
        !left->have_status || !right->have_status ||
        !left->have_stat || !right->have_stat ||
        !left->have_exe || !right->have_exe) {
        return false;
    }

    return left->status.ppid == right->status.ppid &&
           memcmp(left->status.uid, right->status.uid,
                  sizeof(left->status.uid)) == 0 &&
           memcmp(left->status.gid, right->status.gid,
                  sizeof(left->status.gid)) == 0 &&
           left->stat.pid == right->stat.pid &&
           left->stat.state == right->stat.state &&
           left->stat.ppid == right->stat.ppid &&
           left->stat.pgrp == right->stat.pgrp &&
           left->stat.session == right->stat.session &&
           left->stat.tty_nr == right->stat.tty_nr &&
           left->stat.tpgid == right->stat.tpgid &&
           left->stat.starttime == right->stat.starttime &&
           left->exe_device == right->exe_device &&
           left->exe_inode == right->exe_inode &&
           left->exe_mode == right->exe_mode &&
           left->exe_uid == right->exe_uid &&
           left->exe_gid == right->exe_gid &&
           strcmp(left->exe_target, right->exe_target) == 0;
}

static bool sudo_credentials_match(const aco_node *node) {
    return node->status.uid[0] != 0U &&
           node->status.uid[1] == 0U &&
           node->status.uid[2] == 0U &&
           node->status.uid[3] == 0U &&
           node->status.gid[1] == 0U &&
           node->status.gid[2] == 0U &&
           node->status.gid[3] == 0U;
}

aco_result aco_evaluate(aco_report *report) {
    size_t i;
    const aco_node *direct;
    const aco_node *origin;
    const aco_node *outermost_sudo;

    if (report == NULL) {
        return ACO_CHAIN_INCOMPLETE;
    }
    report->sudo_count = 0U;
    report->origin_index = ACO_MAX_NODES;

    if (!report->collection_complete || !report->chain_stable ||
        !report->pidfds_stable || report->node_count == 0U ||
        report->self_pid <= 0 || report->self_parent_pid <= 0) {
        report->reason = "REQUIRED_OBSERVATION_UNAVAILABLE_OR_UNSTABLE";
        return report->result = ACO_CHAIN_INCOMPLETE;
    }

    for (i = 0U; i < report->node_count; i++) {
        if (!report->nodes[i].have_status ||
            !report->nodes[i].have_stat ||
            !report->nodes[i].have_exe ||
            !report->nodes[i].pidfd_open) {
            report->reason = "ANCESTOR_EVIDENCE_OR_PIDFD_MISSING";
            return report->result = ACO_CHAIN_INCOMPLETE;
        }
    }

    direct = &report->nodes[0];
    if (!aco_is_sudo_candidate(direct)) {
        report->reason = "DIRECT_PARENT_IS_NOT_ROOT_OWNED_SETUID_SUDO";
        return report->result = ACO_CHAIN_MISMATCH;
    }
    if (!sudo_credentials_match(direct)) {
        report->reason = "DIRECT_SUDO_CREDENTIALS_DO_NOT_MATCH_EXPECTED_PATTERN";
        return report->result = ACO_CHAIN_MISMATCH;
    }
    if (direct->pid != report->self_parent_pid ||
        direct->stat.session != report->self_sid ||
        direct->stat.tpgid != report->self_pgrp) {
        report->reason = "DIRECT_PARENT_OR_SESSION_RELATION_MISMATCH";
        return report->result = ACO_CHAIN_MISMATCH;
    }

    for (i = 0U; i < report->node_count; i++) {
        if (!aco_is_sudo_candidate(&report->nodes[i])) {
            report->origin_index = i;
            break;
        }
        if (!sudo_credentials_match(&report->nodes[i]) ||
            report->nodes[i].status.uid[0] != direct->status.uid[0]) {
            report->reason = "SUDO_ANCESTOR_CREDENTIALS_MISMATCH";
            return report->result = ACO_CHAIN_MISMATCH;
        }
        report->sudo_count++;
        if (report->sudo_count > 4U) {
            report->reason = "SUDO_ANCESTOR_DEPTH_EXCEEDS_LIMIT";
            return report->result = ACO_CHAIN_INCOMPLETE;
        }
    }

    if (report->origin_index == ACO_MAX_NODES ||
        report->origin_index >= report->node_count ||
        report->origin_index == 0U) {
        report->reason = "ORIGINATING_SHELL_ANCESTOR_NOT_OBSERVED";
        return report->result = ACO_CHAIN_INCOMPLETE;
    }

    for (i = 0U; i + 1U < report->node_count; i++) {
        if (report->nodes[i].stat.ppid != report->nodes[i + 1U].pid) {
            report->reason = "ANCESTOR_PARENT_LINK_MISMATCH";
            return report->result = ACO_CHAIN_MISMATCH;
        }
    }

    origin = &report->nodes[report->origin_index];
    outermost_sudo = &report->nodes[report->sudo_count - 1U];

    if (origin->status.uid[0] != direct->status.uid[0]) {
        report->reason = "ORIGINATING_SHELL_UID_DIFFERS_FROM_SUDO_REAL_UID";
        return report->result = ACO_CHAIN_MISMATCH;
    }
    if (origin->stat.tty_nr == 0 ||
        outermost_sudo->stat.tty_nr == 0 ||
        origin->stat.tty_nr != outermost_sudo->stat.tty_nr ||
        origin->stat.tpgid != outermost_sudo->stat.pgrp) {
        report->reason = "ORIGINATING_TTY_NOT_BOUND_TO_SUDO_MONITOR";
        return report->result = ACO_CHAIN_MISMATCH;
    }
    if (!report->tty_available) {
        report->reason = "HELPER_CONTROLLING_TTY_UNAVAILABLE";
        return report->result = ACO_CHAIN_INCOMPLETE;
    }
    if (report->terminal_sid != report->self_sid ||
        report->foreground_pgrp != report->self_pgrp) {
        report->reason = "HELPER_TTY_SESSION_OR_FOREGROUND_MISMATCH";
        return report->result = ACO_CHAIN_MISMATCH;
    }

    report->reason = "OBSERVATIONS_MATCH_DIRECT_SUDO_AND_ORIGIN_TTY_PATTERN";
    return report->result = ACO_PATTERN_MATCHED_DIAGNOSTICALLY;
}

int aco_collect(aco_report *report) {
    int pidfds[ACO_MAX_NODES];
    int tty_fd = -1;
    pid_t next_pid;
    pid_t initial_parent;
    int32_t tty_sid_before = 0;
    int32_t tty_foreground_before = 0;
    int32_t tty_sid_after = 0;
    int32_t tty_foreground_after = 0;
    bool tty_before = false;
    bool tty_after = false;
    struct timespec pause_time = {0, 20000000L};
    struct timespec remaining_time;
    size_t i;

    if (report == NULL) {
        errno = EINVAL;
        return -1;
    }
    memset(report, 0, sizeof(*report));
    for (i = 0U; i < ACO_MAX_NODES; i++) {
        pidfds[i] = -1;
    }

    report->self_pid = getpid();
    initial_parent = getppid();
    report->self_parent_pid = initial_parent;
    report->self_sid = (int32_t)getsid(0);
    report->self_pgrp = (int32_t)getpgrp();
    report->chain_stable = true;
    report->pidfds_stable = true;
    report->collection_complete = true;

    tty_fd = open("/dev/tty", O_RDONLY | O_CLOEXEC | O_NOCTTY);
    if (tty_fd >= 0) {
        tty_before = tty_snapshot(tty_fd, &tty_sid_before,
                                  &tty_foreground_before);
        if (!tty_before) {
            report->tty_errno = errno;
        }
    } else {
        report->tty_errno = errno;
    }
    report->tty_available = tty_before;
    report->terminal_sid = tty_sid_before;
    report->foreground_pgrp = tty_foreground_before;

    next_pid = initial_parent;
    while (next_pid > 1 && report->node_count < ACO_MAX_NODES) {
        size_t index = report->node_count;
        aco_node *node = &report->nodes[index];

        pidfds[index] = pidfd_open_local(next_pid);
        if (pidfds[index] < 0) {
            report->collection_complete = false;
            report->pidfds_stable = false;
            break;
        }
        node->pidfd_open = true;
        if (!pidfd_alive(pidfds[index]) ||
            !capture_node(next_pid, node)) {
            report->collection_complete = false;
            break;
        }
        node->pidfd_open = true;
        report->node_count++;

        if (!aco_is_sudo_candidate(node)) {
            if (index == 0U) {
                break;
            }
            break;
        }
        next_pid = node->stat.ppid;
    }

    if (report->node_count == ACO_MAX_NODES &&
        report->nodes[ACO_MAX_NODES - 1U].stat.ppid > 1) {
        report->collection_complete = false;
    }

    if (report->node_count > 0U && report->collection_complete) {
        for (i = 0U; i < report->node_count; i++) {
            aco_node second;
            if (!pidfd_alive(pidfds[i])) {
                report->pidfds_stable = false;
                report->chain_stable = false;
                continue;
            }
            if (!capture_node(report->nodes[i].pid, &second)) {
                report->collection_complete = false;
                continue;
            }
            if (!aco_node_equal(&report->nodes[i], &second)) {
                report->chain_stable = false;
            }
            if (!pidfd_alive(pidfds[i])) {
                report->pidfds_stable = false;
                report->chain_stable = false;
            }
        }
    } else {
        report->collection_complete = false;
    }

    while (nanosleep(&pause_time, &remaining_time) != 0 && errno == EINTR) {
        pause_time = remaining_time;
    }

    if (getppid() != initial_parent ||
        (int32_t)getsid(0) != report->self_sid ||
        (int32_t)getpgrp() != report->self_pgrp) {
        report->chain_stable = false;
    }

    if (tty_fd >= 0) {
        tty_after = tty_snapshot(tty_fd, &tty_sid_after,
                                 &tty_foreground_after);
        if (!tty_after || !tty_before ||
            tty_sid_after != tty_sid_before ||
            tty_foreground_after != tty_foreground_before) {
            report->chain_stable = false;
        }
        (void)close(tty_fd);
    }

    for (i = 0U; i < ACO_MAX_NODES; i++) {
        if (pidfds[i] >= 0) {
            if (!pidfd_alive(pidfds[i])) {
                report->pidfds_stable = false;
            }
            (void)close(pidfds[i]);
        }
    }

    (void)aco_evaluate(report);
    return 0;
}

static void print_escaped(FILE *stream, const char *value) {
    const unsigned char *cursor = (const unsigned char *)value;
    while (*cursor != '\0') {
        if (*cursor >= 0x20U && *cursor <= 0x7eU &&
            *cursor != (unsigned char)'\\') {
            (void)fputc((int)*cursor, stream);
        } else if (*cursor == (unsigned char)'\\') {
            (void)fputs("\\\\", stream);
        } else {
            (void)fprintf(stream, "\\x%02x", (unsigned int)*cursor);
        }
        cursor++;
    }
}

static const char *result_name(aco_result result) {
    switch (result) {
    case ACO_PATTERN_MATCHED_DIAGNOSTICALLY:
        return "CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY";
    case ACO_CHAIN_MISMATCH:
        return "CHAIN_MISMATCH";
    case ACO_CHAIN_INCOMPLETE:
        return "CHAIN_INCOMPLETE";
    }
    return "CHAIN_INCOMPLETE";
}

void aco_print_report(FILE *stream, const aco_report *report) {
    size_t i;

    if (stream == NULL || report == NULL) {
        return;
    }
    fprintf(stream, "observer_pid=%ld\n", (long)report->self_pid);
    fprintf(stream, "observer_ppid=%ld\n", (long)report->self_parent_pid);
    fprintf(stream, "observer_sid=%" PRId32 "\n", report->self_sid);
    fprintf(stream, "observer_pgrp=%" PRId32 "\n", report->self_pgrp);
    fprintf(stream, "result=%s\n", result_name(report->result));
    fprintf(stream, "reason=%s\n",
            report->reason == NULL ? "UNSPECIFIED" : report->reason);
    fprintf(stream, "chain_stable=%s\n",
            report->chain_stable ? "yes" : "no");
    fprintf(stream, "pidfds_stable=%s\n",
            report->pidfds_stable ? "yes" : "no");
    fprintf(stream, "collection_complete=%s\n",
            report->collection_complete ? "yes" : "no");
    fprintf(stream, "sudo_ancestor_count=%zu\n", report->sudo_count);
    fprintf(stream, "origin_ancestor_index=%zu\n", report->origin_index);
    for (i = 0U; i < report->node_count; i++) {
        const aco_node *node = &report->nodes[i];
        fprintf(stream, "chain[%zu].pid=%ld\n", i, (long)node->pid);
        fprintf(stream, "chain[%zu].ppid=%" PRId32 "\n", i,
                node->stat.ppid);
        fprintf(stream, "chain[%zu].exe=", i);
        if (node->have_exe) {
            print_escaped(stream, node->exe_target);
        } else {
            (void)fputs("UNAVAILABLE", stream);
        }
        (void)fputc('\n', stream);
        if (node->have_status) {
            fprintf(stream, "chain[%zu].uid=%" PRIu32 "/%" PRIu32
                            "/%" PRIu32 "/%" PRIu32 "\n", i,
                    node->status.uid[0], node->status.uid[1],
                    node->status.uid[2], node->status.uid[3]);
            fprintf(stream, "chain[%zu].gid=%" PRIu32 "/%" PRIu32
                            "/%" PRIu32 "/%" PRIu32 "\n", i,
                    node->status.gid[0], node->status.gid[1],
                    node->status.gid[2], node->status.gid[3]);
        }
        if (node->have_stat) {
            fprintf(stream, "chain[%zu].sid=%" PRId32 "\n", i,
                    node->stat.session);
            fprintf(stream, "chain[%zu].pgrp=%" PRId32 "\n", i,
                    node->stat.pgrp);
            fprintf(stream, "chain[%zu].tty_nr=%" PRId64 "\n", i,
                    node->stat.tty_nr);
            fprintf(stream, "chain[%zu].tpgid=%" PRId32 "\n", i,
                    node->stat.tpgid);
            fprintf(stream, "chain[%zu].starttime=%" PRIu64 "\n", i,
                    node->stat.starttime);
        }
        fprintf(stream, "chain[%zu].pidfd=%s\n", i,
                node->pidfd_open ? "OPEN" : "UNAVAILABLE");
        fprintf(stream, "chain[%zu].sudo_candidate=%s\n", i,
                aco_is_sudo_candidate(node) ? "yes" : "no");
    }
    fprintf(stream, "tty=%s\n", report->tty_available ? "AVAILABLE" :
            "UNAVAILABLE");
    if (report->tty_available) {
        fprintf(stream, "terminal_sid=%" PRId32 "\n",
                report->terminal_sid);
        fprintf(stream, "foreground_pgrp=%" PRId32 "\n",
                report->foreground_pgrp);
    } else if (report->tty_errno != 0) {
        fprintf(stream, "tty_errno=%d\n", report->tty_errno);
    }
    fprintf(stream, "AUTHORIZATION=NOT_PROVIDED\n");
}
