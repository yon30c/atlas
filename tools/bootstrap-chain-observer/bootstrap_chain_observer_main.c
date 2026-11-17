#include "bootstrap_chain_observer.h"

#include <stdio.h>

int main(int argc, char **argv) {
    aco_report report;

    (void)argv;
    if (argc != 1) {
        (void)fprintf(stderr, "Usage: atlas-bootstrap-chain-observer\n");
        return 64;
    }
    if (aco_collect(&report) != 0) {
        (void)fprintf(stderr, "chain observer: collection failed\n");
        return 1;
    }
    aco_print_report(stdout, &report);

    switch (report.result) {
    case ACO_PATTERN_MATCHED_DIAGNOSTICALLY:
        return 0;
    case ACO_CHAIN_INCOMPLETE:
        return 2;
    case ACO_CHAIN_MISMATCH:
        return 3;
    }
    return 1;
}
