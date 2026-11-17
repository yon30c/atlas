#include "bootstrap_observer_linux.h"

#include <stdio.h>
#include <string.h>

static int exit_code(bv_observation_result result) {
    switch (result) {
    case BV_OBSERVATION_CONSISTENT:
        return 0;
    case BV_OBSERVATION_INCOMPLETE:
        return 2;
    case BV_OBSERVATION_INCONSISTENT:
        return 3;
    default:
        return 1;
    }
}

int main(int argc, char **argv) {
    bo_report report;
    unsigned hold_ms = 0;

    if (argc == 3 && strcmp(argv[1], "--hold-ms") == 0) {
        if (!bo_parse_hold_ms(argv[2], &hold_ms)) {
            fprintf(stderr, "Uso: atlas-bootstrap-observer [--hold-ms 1000..30000]\n");
            return 64;
        }
    } else if (argc != 1) {
        fprintf(stderr, "Uso: atlas-bootstrap-observer [--hold-ms 1000..30000]\n");
        return 64;
    }

    if (bo_collect(&report) != 0) {
        perror("No se pudo iniciar la observación");
        return 1;
    }
    if (hold_ms != 0U && bo_run_hold(&report, hold_ms) != 0) {
        perror("No se pudo muestrear el TTY");
        return 1;
    }

    bo_print_report(stdout, &report);
    return exit_code(report.result);
}
