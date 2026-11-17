#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <termios.h>
#include <unistd.h>
#include <linux/limits.h>

static void print_error(const char *label) {
    fprintf(stderr, "%s: %s\n", label, strerror(errno));
}

static int read_parent_status(pid_t pid) {
    char path[64];
    char buffer[16384];
    ssize_t n;
    int fd;
    unsigned int ruid, euid, suid, fsuid;
    unsigned int rgid, egid, sgid, fsgid;
    long parent_pid = -1;

    if (snprintf(path, sizeof(path), "/proc/%ld/status", (long)pid) >= (int)sizeof(path)) {
        fprintf(stderr, "Ruta /proc truncada\n");
        return -1;
    }

    fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        print_error("No se pudo abrir status del padre");
        return -1;
    }

    n = read(fd, buffer, sizeof(buffer) - 1);
    close(fd);
    if (n < 0) {
        print_error("No se pudo leer status del padre");
        return -1;
    }
    if (n == 0 || n == (ssize_t)(sizeof(buffer) - 1)) {
        fprintf(stderr, "status del padre vacío o excede el límite\n");
        return -1;
    }
    buffer[n] = '\0';

    {
        char *line = buffer;
        bool got_uid = false, got_gid = false, got_ppid = false;
        while (line && *line) {
            char *next = strchr(line, '\n');
            if (next) *next++ = '\0';

            if (strncmp(line, "Uid:", 4) == 0) {
                if (sscanf(line + 4, "%u %u %u %u", &ruid, &euid, &suid, &fsuid) != 4) {
                    fprintf(stderr, "Formato Uid inesperado\n");
                    return -1;
                }
                got_uid = true;
            } else if (strncmp(line, "Gid:", 4) == 0) {
                if (sscanf(line + 4, "%u %u %u %u", &rgid, &egid, &sgid, &fsgid) != 4) {
                    fprintf(stderr, "Formato Gid inesperado\n");
                    return -1;
                }
                got_gid = true;
            } else if (strncmp(line, "PPid:", 5) == 0) {
                if (sscanf(line + 5, "%ld", &parent_pid) != 1) {
                    fprintf(stderr, "Formato PPid inesperado\n");
                    return -1;
                }
                got_ppid = true;
            }
            line = next;
        }

        if (!got_uid || !got_gid || !got_ppid) {
            fprintf(stderr, "Faltan campos obligatorios en /proc status\n");
            return -1;
        }
    }

    printf("Padre - PID: %ld\n", (long)pid);
    printf("Padre - PPID: %ld\n", parent_pid);
    printf("Padre - UID real/efectivo/saved/fs: %u/%u/%u/%u\n",
           ruid, euid, suid, fsuid);
    printf("Padre - GID real/efectivo/saved/fs: %u/%u/%u/%u\n",
           rgid, egid, sgid, fsgid);
    return 0;
}

static void inspect_parent_session(pid_t pid) {
    char path[64];
    char buffer[4096];
    ssize_t n;
    int fd;
    char *close_paren;
    char state;
    long ppid, pgrp, session, tpgid;
    int tty_nr;

    printf("\n===== SESIÓN Y DESCRIPTORES DEL PADRE (DIAGNÓSTICO) =====\n");

    if (snprintf(path, sizeof(path), "/proc/%ld/stat", (long)pid) >= (int)sizeof(path)) {
        fprintf(stderr, "Ruta /proc stat truncada\n");
        return;
    }

    fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        print_error("No se pudo abrir stat del padre");
        return;
    }
    n = read(fd, buffer, sizeof(buffer) - 1);
    close(fd);
    if (n <= 0 || n >= (ssize_t)(sizeof(buffer) - 1)) {
        fprintf(stderr, "stat del padre vacío o excede el límite\n");
        return;
    }
    buffer[n] = '\0';

    /* comm puede contener espacios y paréntesis: separar por el último ')'. */
    close_paren = strrchr(buffer, ')');
    if (!close_paren ||
        sscanf(close_paren + 1, " %c %ld %ld %ld %d %ld",
               &state, &ppid, &pgrp, &session, &tty_nr, &tpgid) != 6) {
        fprintf(stderr, "No se pudo parsear stat del padre\n");
        return;
    }

    printf("Padre stat - estado: %c; PPID: %ld; PGID: %ld; SID: %ld\n",
           state, ppid, pgrp, session);
    printf("Padre stat - tty_nr: %d; TPGID: %ld\n", tty_nr, tpgid);
    printf("Nota: tty_nr=0 suele indicar que el padre no tiene TTY controlador.\n");

    for (int i = 0; i <= 2; i++) {
        char fd_path[96];
        char target[PATH_MAX + 1];
        ssize_t target_len;

        if (snprintf(fd_path, sizeof(fd_path), "/proc/%ld/fd/%d",
                     (long)pid, i) >= (int)sizeof(fd_path)) {
            continue;
        }
        target_len = readlink(fd_path, target, sizeof(target) - 1);
        if (target_len < 0) {
            printf("Padre fd %d: no disponible (%s)\n", i, strerror(errno));
        } else {
            target[target_len] = '\0';
            printf("Padre fd %d -> %s\n", i, target);
        }
    }
}

static void inspect_parent(pid_t parent_pid) {
    char path[64];
    char target[PATH_MAX + 1];
    ssize_t target_len;
    struct stat st;
    int exe_fd = -1;
    int pidfd = -1;

    printf("\n===== PROCESO PADRE DIRECTO (DIAGNÓSTICO) =====\n");
    printf("PID padre capturado: %ld\n", (long)parent_pid);

#ifdef SYS_pidfd_open
    pidfd = (int)syscall(SYS_pidfd_open, parent_pid, 0);
    if (pidfd < 0) {
        print_error("pidfd_open no disponible/falló");
    } else {
        struct pollfd pfd = {.fd = pidfd, .events = POLLIN};
        int pr = poll(&pfd, 1, 0);
        if (pr < 0) {
            print_error("poll(pidfd) falló");
        } else {
            printf("pidfd: abierto; estado inmediato: %s\n",
                   pr == 0 ? "proceso no reportado como terminado" : "evento/terminación reportada");
        }
    }
#else
    printf("pidfd_open: no existe SYS_pidfd_open en headers de compilación\n");
#endif

    if (snprintf(path, sizeof(path), "/proc/%ld/exe", (long)parent_pid) >= (int)sizeof(path)) {
        fprintf(stderr, "Ruta /proc exe truncada\n");
        goto done;
    }

    exe_fd = open(path, O_RDONLY | O_CLOEXEC);
    if (exe_fd < 0) {
        print_error("No se pudo abrir /proc/PID/exe");
    } else if (fstat(exe_fd, &st) < 0) {
        print_error("fstat del ejecutable padre falló");
    } else {
        printf("Padre exe - dispositivo: %" PRIuMAX "\n", (uintmax_t)st.st_dev);
        printf("Padre exe - inode: %" PRIuMAX "\n", (uintmax_t)st.st_ino);
        printf("Padre exe - propietario UID/GID: %lu/%lu\n",
               (unsigned long)st.st_uid, (unsigned long)st.st_gid);
        printf("Padre exe - modo: %04o; regular: %s\n",
               (unsigned int)(st.st_mode & 07777),
               S_ISREG(st.st_mode) ? "sí" : "no");
    }

    target_len = readlink(path, target, sizeof(target) - 1);
    if (target_len < 0) {
        print_error("readlink de ejecutable padre falló");
    } else {
        target[target_len] = '\0';
        printf("Padre exe - destino informativo: %s\n", target);
    }

    (void)read_parent_status(parent_pid);
    inspect_parent_session(parent_pid);

    if (getppid() != parent_pid) {
        printf("ADVERTENCIA: getppid() cambió durante la inspección\n");
    } else {
        printf("Relación PPID inmediata: sigue coincidiendo al final\n");
    }

done:
    if (exe_fd >= 0) close(exe_fd);
    if (pidfd >= 0) close(pidfd);
}


#define MAX_ANCESTORS 12

/*
 * Read-only ancestry walk for design diagnostics. /proc is a time-varying
 * observation; this output is deliberately not an authorization decision.
 */
static bool read_status_identity(pid_t pid, long *ppid_out,
                                 unsigned int uid[4], unsigned int gid[4]) {
    char path[64], buffer[16384];
    ssize_t n;
    int fd;
    bool got_ppid = false, got_uid = false, got_gid = false;

    if (snprintf(path, sizeof(path), "/proc/%ld/status", (long)pid) >= (int)sizeof(path))
        return false;
    fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return false;
    n = read(fd, buffer, sizeof(buffer) - 1);
    close(fd);
    if (n <= 0 || n >= (ssize_t)(sizeof(buffer) - 1)) return false;
    buffer[n] = '\0';

    for (char *line = buffer; line && *line;) {
        char *next = strchr(line, '\n');
        if (next) *next++ = '\0';
        if (strncmp(line, "PPid:", 5) == 0)
            got_ppid = sscanf(line + 5, "%ld", ppid_out) == 1;
        else if (strncmp(line, "Uid:", 4) == 0)
            got_uid = sscanf(line + 4, "%u %u %u %u",
                             &uid[0], &uid[1], &uid[2], &uid[3]) == 4;
        else if (strncmp(line, "Gid:", 4) == 0)
            got_gid = sscanf(line + 4, "%u %u %u %u",
                             &gid[0], &gid[1], &gid[2], &gid[3]) == 4;
        line = next;
    }
    return got_ppid && got_uid && got_gid;
}

static void inspect_ancestor_chain(pid_t first_pid) {
    pid_t pid = first_pid;
    printf("\n===== CADENA DE ANCESTROS (DIAGNÓSTICO; NO AUTORIZA) =====\n");

    for (int level = 1; level <= MAX_ANCESTORS && pid > 1; level++) {
        char path[96], target[PATH_MAX + 1], statbuf[4096];
        ssize_t n, target_len;
        unsigned int uid[4] = {0}, gid[4] = {0};
        long ppid_before = -1, ppid_after = -1;
        long stat_ppid = -1, pgrp = -1, session = -1, tpgid = -1;
        int tty_nr = 0, pidfd = -1, exe_fd = -1;
        struct stat exe_st;
        bool stable = false;

        if (!read_status_identity(pid, &ppid_before, uid, gid)) {
            printf("\nNivel %d PID %ld: status no disponible/parseable (%s); se detiene\n",
                   level, (long)pid, strerror(errno));
            break;
        }

        printf("\n--- NIVEL %d | PID %ld ---\n", level, (long)pid);
        printf("Credenciales UID real/efectivo/saved/fs: %u/%u/%u/%u\n",
               uid[0], uid[1], uid[2], uid[3]);
        printf("Credenciales GID real/efectivo/saved/fs: %u/%u/%u/%u\n",
               gid[0], gid[1], gid[2], gid[3]);

#ifdef SYS_pidfd_open
        pidfd = (int)syscall(SYS_pidfd_open, pid, 0);
        if (pidfd < 0) {
            printf("pidfd: no disponible (%s)\n", strerror(errno));
        } else {
            struct pollfd pfd = {.fd = pidfd, .events = POLLIN};
            int pr = poll(&pfd, 1, 0);
            printf("pidfd: abierto; poll inmediato=%s\n",
                   pr == 0 ? "sin evento" : (pr > 0 ? "evento" : "error"));
        }
#endif

        if (snprintf(path, sizeof(path), "/proc/%ld/exe", (long)pid) < (int)sizeof(path)) {
            exe_fd = open(path, O_RDONLY | O_CLOEXEC);
            if (exe_fd >= 0 && fstat(exe_fd, &exe_st) == 0) {
                printf("Ejecutable: dev=%" PRIuMAX " inode=%" PRIuMAX
                       " owner=%lu:%lu mode=%04o regular=%s\n",
                       (uintmax_t)exe_st.st_dev, (uintmax_t)exe_st.st_ino,
                       (unsigned long)exe_st.st_uid, (unsigned long)exe_st.st_gid,
                       (unsigned int)(exe_st.st_mode & 07777),
                       S_ISREG(exe_st.st_mode) ? "sí" : "no");
            } else {
                printf("Ejecutable: no verificable (%s)\n", strerror(errno));
            }
            target_len = readlink(path, target, sizeof(target) - 1);
            if (target_len >= 0) {
                target[target_len] = '\0';
                printf("Destino exe (informativo): %s\n", target);
            }
        }

        if (snprintf(path, sizeof(path), "/proc/%ld/stat", (long)pid) < (int)sizeof(path)) {
            int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
            if (fd >= 0) {
                n = read(fd, statbuf, sizeof(statbuf) - 1);
                close(fd);
                if (n > 0 && n < (ssize_t)(sizeof(statbuf) - 1)) {
                    char *close_paren;
                    statbuf[n] = '\0';
                    close_paren = strrchr(statbuf, ')');
                    if (close_paren &&
                        sscanf(close_paren + 1, " %*c %ld %ld %ld %d %ld",
                               &stat_ppid, &pgrp, &session, &tty_nr, &tpgid) == 5) {
                        printf("stat: PPID=%ld PGID=%ld SID=%ld tty_nr=%d TPGID=%ld\n",
                               stat_ppid, pgrp, session, tty_nr, tpgid);
                    } else {
                        printf("stat: no se pudo parsear\n");
                    }
                }
            }
        }

        for (int fdno = 0; fdno <= 2; fdno++) {
            char fdpath[96];
            if (snprintf(fdpath, sizeof(fdpath), "/proc/%ld/fd/%d",
                         (long)pid, fdno) >= (int)sizeof(fdpath)) continue;
            target_len = readlink(fdpath, target, sizeof(target) - 1);
            if (target_len >= 0) {
                target[target_len] = '\0';
                printf("fd %d -> %s\n", fdno, target);
            } else {
                printf("fd %d -> no disponible (%s)\n", fdno, strerror(errno));
            }
        }

        stable = read_status_identity(pid, &ppid_after, uid, gid) &&
                 ppid_before == ppid_after;
        if (pidfd >= 0) {
            struct pollfd pfd = {.fd = pidfd, .events = POLLIN};
            int pr = poll(&pfd, 1, 0);
            if (pr != 0) stable = false;
        }
        printf("Revalidación del ancestro: %s\n",
               stable ? "PID vivo y PPID sin cambio observado" :
                        "inestable/no verificable durante la lectura");

        if (exe_fd >= 0) close(exe_fd);
        if (pidfd >= 0) close(pidfd);

        if (stat_ppid > 0 && stat_ppid != ppid_before) {
            printf("ADVERTENCIA: PPID de status y stat no coinciden (%ld/%ld)\n",
                   ppid_before, stat_ppid);
        }
        if (ppid_before <= 1 || ppid_before == pid) break;
        pid = (pid_t)ppid_before;
    }

    printf("\nFin de recorrido de ancestros. Es una secuencia de lecturas no atómica.\n");
}

static void inspect_tty(void) {
    int fd;
    struct stat st;
    pid_t terminal_sid, process_sid, foreground_pgrp, process_pgrp;

    printf("\n===== TTY CONTROLADOR (DIAGNÓSTICO) =====\n");
    fd = open("/dev/tty", O_RDONLY | O_CLOEXEC | O_NOCTTY | O_NOFOLLOW);
    if (fd < 0) {
        print_error("No se pudo abrir /dev/tty");
        return;
    }

    if (!isatty(fd)) {
        fprintf(stderr, "/dev/tty abierto no se identifica como terminal\n");
        close(fd);
        return;
    }

    if (fstat(fd, &st) < 0) {
        print_error("fstat del TTY falló");
        close(fd);
        return;
    }

    terminal_sid = tcgetsid(fd);
    if (terminal_sid < 0) print_error("tcgetsid falló");
    else printf("Terminal SID: %ld\n", (long)terminal_sid);

    process_sid = getsid(0);
    if (process_sid < 0) print_error("getsid falló");
    else printf("Proceso SID: %ld\n", (long)process_sid);

    foreground_pgrp = tcgetpgrp(fd);
    if (foreground_pgrp < 0) print_error("tcgetpgrp falló");
    else printf("Grupo foreground: %ld\n", (long)foreground_pgrp);

    process_pgrp = getpgrp();
    printf("Grupo del proceso: %ld\n", (long)process_pgrp);
    printf("TTY - dispositivo: %" PRIuMAX "\n", (uintmax_t)st.st_rdev);
    printf("TTY - propietario UID/GID: %lu/%lu\n",
           (unsigned long)st.st_uid, (unsigned long)st.st_gid);
    printf("TTY - modo: %04o\n", (unsigned int)(st.st_mode & 07777));

    close(fd);
}

int main(int argc, char **argv) {
    pid_t self_pid, parent_pid;
    (void)argv;

    if (argc != 1) {
        fprintf(stderr, "Uso: bootstrap-probe (sin argumentos)\n");
        return 2;
    }

    self_pid = getpid();
    parent_pid = getppid();

    printf("ATENCIÓN: herramienta de diagnóstico solamente.\n");
    printf("No autentica, no autoriza, no firma y no emite pruebas.\n");
    printf("No debe instalarse como helper privilegiado.\n\n");

    printf("===== PROCESO ACTUAL =====\n");
    printf("PID: %ld\n", (long)self_pid);
    printf("PPID capturado: %ld\n", (long)parent_pid);
    printf("UID real/efectivo: %lu/%lu\n",
           (unsigned long)getuid(), (unsigned long)geteuid());
    printf("GID real/efectivo: %lu/%lu\n",
           (unsigned long)getgid(), (unsigned long)getegid());
    printf("SID: %ld\n", (long)getsid(0));
    printf("PGID: %ld\n", (long)getpgrp());

    inspect_parent(parent_pid);
    inspect_ancestor_chain(parent_pid);
    inspect_tty();

    printf("\nFIN DEL DIAGNÓSTICO. Ningún resultado equivale a autorización.\n");
    return 0;
}
