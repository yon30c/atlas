#include "bootstrap_observer_linux.h"

#include <assert.h>
#include <stdio.h>

static void test_hold_arguments(void) {
    unsigned milliseconds = 0;

    assert(bo_parse_hold_ms("1000", &milliseconds));
    assert(milliseconds == 1000U);
    assert(bo_parse_hold_ms("30000", &milliseconds));
    assert(milliseconds == 30000U);
    assert(bo_parse_hold_ms("1500", &milliseconds));
    assert(milliseconds == 1500U);

    assert(!bo_parse_hold_ms(NULL, &milliseconds));
    assert(!bo_parse_hold_ms("", &milliseconds));
    assert(!bo_parse_hold_ms("999", &milliseconds));
    assert(!bo_parse_hold_ms("30001", &milliseconds));
    assert(!bo_parse_hold_ms("0", &milliseconds));
    assert(!bo_parse_hold_ms("-1000", &milliseconds));
    assert(!bo_parse_hold_ms("+1000", &milliseconds));
    assert(!bo_parse_hold_ms("1s", &milliseconds));
    assert(!bo_parse_hold_ms("999999999999999999999999", &milliseconds));
}

static void test_hold_execution_bounds(void) {
    bo_report report = {0};

    assert(bo_run_hold(NULL, 1000U) == -1);
    assert(bo_run_hold(&report, 999U) == -1);
    assert(bo_run_hold(&report, 30001U) == -1);
}

static void test_live_observation_smoke(void) {
    bo_report report;

    assert(bo_collect(&report) == 0);
    assert(report.self_pid > 0);
    assert(report.parent_pid > 0);
    assert(report.self_pid != report.parent_pid);
    assert(report.result == BV_OBSERVATION_CONSISTENT ||
           report.result == BV_OBSERVATION_INCONSISTENT ||
           report.result == BV_OBSERVATION_INCOMPLETE);
}

int main(void) {
    test_hold_arguments();
    test_hold_execution_bounds();
    test_live_observation_smoke();
    puts("bootstrap-observer V2: unit and live smoke tests passed");
    return 0;
}
