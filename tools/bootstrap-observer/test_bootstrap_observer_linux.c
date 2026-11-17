#include "bootstrap_observer_linux.h"

#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>

static void test_output_escaping(void) {
    bo_report report = {0};
    FILE *stream = tmpfile();
    char output[2048];
    size_t count;

    assert(stream != NULL);
    report.exe_first_available = true;
    strcpy(report.exe_target, "parent\\nAUTHORIZATION=FORGED");
    bo_print_report(stream, &report);
    rewind(stream);
    count = fread(output, 1U, sizeof(output) - 1U, stream);
    output[count] = '\\0';

    assert(strstr(output,
                  "parent_exe_target=parent\\x5cnAUTHORIZATION=FORGED") != NULL);
    assert(strstr(output, "\\nAUTHORIZATION=FORGED\\n") == NULL);
    assert(fclose(stream) == 0);
}

static void test_read_classification(void) {
    assert(bo_classify_read(10U, 10U, 0) == BV_OK);
    assert(bo_classify_read(11U, 10U, 0) == BV_TOO_LARGE);
    assert(bo_classify_read(0U, 10U, EOVERFLOW) == BV_TOO_LARGE);
    assert(bo_classify_read(0U, 10U, EACCES) == BV_TRUNCATED);
    assert(bo_classify_read(0U, 10U, 0) == BV_TRUNCATED);
}

static void test_pidfd_classification(void) {
    assert(bo_pidfd_state_from_poll(0, 0) == BV_PIDFD_OPEN_UNSIGNALED);
    assert(bo_pidfd_state_from_poll(1, POLLIN) == BV_PIDFD_SIGNALED);
    assert(bo_pidfd_state_from_poll(-1, 0) == BV_PIDFD_NOT_REQUESTED);
    assert(bo_pidfd_state_from_poll(1, POLLERR) == BV_PIDFD_NOT_REQUESTED);
    assert(bo_pidfd_state_from_poll(1, POLLNVAL) == BV_PIDFD_NOT_REQUESTED);
}

static void test_snapshot_comparison(void) {
    bv_status status_a = {0};
    bv_status status_b = {0};
    bv_stat stat_a = {0};
    bv_stat stat_b = {0};

    status_a.ppid = 1;
    status_a.uid[0] = 1000;
    status_a.gid[0] = 100;
    status_b = status_a;

    stat_a.pid = 10;
    stat_a.state = 'S';
    stat_a.ppid = 1;
    stat_a.pgrp = 10;
    stat_a.session = 10;
    stat_a.tty_nr = 34816;
    stat_a.tpgid = 10;
    stat_a.starttime = 9876;
    stat_b = stat_a;

    assert(bo_session_matches(10, 10));
    assert(!bo_session_matches(10, 11));
    assert(!bo_session_matches(0, 0));
    assert(bo_parent_samples_match(&status_a, &stat_a, &status_b, &stat_b));
    status_b.uid[0]++;
    assert(!bo_parent_samples_match(&status_a, &stat_a, &status_b, &stat_b));
    status_b = status_a;
    stat_b.starttime++;
    assert(!bo_parent_samples_match(&status_a, &stat_a, &status_b, &stat_b));
    assert(!bo_parent_samples_match(NULL, &stat_a, &status_b, &stat_b));
}

static void test_executable_comparison(void) {
    assert(bo_executable_samples_match(1, 2, 0755, 0, 0,
                                       1, 2, 0755, 0, 0));
    assert(!bo_executable_samples_match(1, 2, 0755, 0, 0,
                                        1, 3, 0755, 0, 0));
    assert(!bo_executable_samples_match(1, 2, 0755, 0, 0,
                                        1, 2, 04755, 0, 0));
}

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
    test_output_escaping();
    test_read_classification();
    test_pidfd_classification();
    test_snapshot_comparison();
    test_executable_comparison();
    test_hold_arguments();
    test_hold_execution_bounds();
    test_live_observation_smoke();
    puts("bootstrap-observer V2: unit and live smoke tests passed");
    return 0;
}
