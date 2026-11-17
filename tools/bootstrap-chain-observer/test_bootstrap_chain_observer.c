#define _GNU_SOURCE

#include "bootstrap_chain_observer.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static void set_exe(aco_node *node, const char *path, uint32_t mode) {
    node->have_exe = true;
    node->exe_device = 1U;
    node->exe_inode = 2U;
    node->exe_mode = mode;
    node->exe_uid = 0U;
    node->exe_gid = 0U;
    (void)snprintf(node->exe_target, sizeof(node->exe_target), "%s", path);
}

static void set_sudo(aco_node *node, int32_t pid, int32_t ppid,
                     int32_t sid, int32_t pgrp, int32_t tty,
                     int32_t tpgid, uint64_t start) {
    memset(node, 0, sizeof(*node));
    node->pid = (pid_t)pid;
    node->have_status = true;
    node->have_stat = true;
    node->status.ppid = ppid;
    node->status.uid[0] = 1000U;
    node->status.uid[1] = 0U;
    node->status.uid[2] = 0U;
    node->status.uid[3] = 0U;
    node->status.gid[0] = 0U;
    node->status.gid[1] = 0U;
    node->status.gid[2] = 0U;
    node->status.gid[3] = 0U;
    node->stat.pid = pid;
    node->stat.state = 'S';
    node->stat.ppid = ppid;
    node->stat.pgrp = pgrp;
    node->stat.session = sid;
    node->stat.tty_nr = tty;
    node->stat.tpgid = tpgid;
    node->stat.starttime = start;
    node->pidfd_open = true;
    set_exe(node, "/usr/bin/sudo", (uint32_t)(S_IFREG | S_ISUID | 0755));
}

static void set_shell(aco_node *node, int32_t pid, int32_t ppid,
                      int32_t tty, int32_t tpgid) {
    memset(node, 0, sizeof(*node));
    node->pid = (pid_t)pid;
    node->have_status = true;
    node->have_stat = true;
    node->status.ppid = ppid;
    node->status.uid[0] = 1000U;
    node->status.uid[1] = 1000U;
    node->status.uid[2] = 1000U;
    node->status.uid[3] = 1000U;
    node->status.gid[0] = 1000U;
    node->status.gid[1] = 1000U;
    node->status.gid[2] = 1000U;
    node->status.gid[3] = 1000U;
    node->stat.pid = pid;
    node->stat.state = 'S';
    node->stat.ppid = ppid;
    node->stat.pgrp = pid;
    node->stat.session = pid;
    node->stat.tty_nr = tty;
    node->stat.tpgid = tpgid;
    node->stat.starttime = 300U;
    node->pidfd_open = true;
    set_exe(node, "/usr/bin/bash", (uint32_t)(S_IFREG | 0755));
}

static void valid_fixture(aco_report *report) {
    memset(report, 0, sizeof(*report));
    report->self_pid = 300;
    report->self_parent_pid = 200;
    report->self_sid = 200;
    report->self_pgrp = 300;
    report->self_stat_available = true;
    report->self_stat.pid = 300;
    report->self_stat.state = 'R';
    report->self_stat.ppid = 200;
    report->self_stat.pgrp = 300;
    report->self_stat.session = 200;
    report->self_stat.tty_nr = 34818;
    report->self_stat.tpgid = 300;
    report->self_stat.starttime = 400U;
    report->tty_available = true;
    report->terminal_sid = 200;
    report->foreground_pgrp = 300;
    report->chain_stable = true;
    report->pidfds_stable = true;
    report->collection_complete = true;
    report->node_count = 3U;
    set_sudo(&report->nodes[0], 200, 201, 200, 200, 34818, 300, 100U);
    set_sudo(&report->nodes[1], 201, 202, 201, 201, 34816, 201, 200U);
    set_shell(&report->nodes[2], 202, 203, 34816, 201);
}

static void test_direct_sudo_pattern(void) {
    aco_report report;
    valid_fixture(&report);
    assert(aco_evaluate(&report) == ACO_PATTERN_MATCHED_DIAGNOSTICALLY);
    assert(report.sudo_count == 2U);
    assert(report.origin_index == 2U);
}

static void test_shell_wrapper_rejected(void) {
    aco_report report;
    valid_fixture(&report);
    set_shell(&report.nodes[0], 200, 201, 34818, 300);
    assert(aco_evaluate(&report) == ACO_CHAIN_MISMATCH);
    assert(strcmp(report.reason,
                  "DIRECT_PARENT_IS_NOT_ROOT_OWNED_SETUID_SUDO") == 0);
}

static void test_bad_sudo_credentials_rejected(void) {
    aco_report report;
    valid_fixture(&report);
    report.nodes[0].status.uid[1] = 1000U;
    assert(aco_evaluate(&report) == ACO_CHAIN_MISMATCH);
}

static void test_missing_origin_tty_rejected(void) {
    aco_report report;
    valid_fixture(&report);
    report.nodes[2].stat.tty_nr = 0;
    assert(aco_evaluate(&report) == ACO_CHAIN_MISMATCH);
    assert(strcmp(report.reason,
                  "ORIGINATING_TTY_NOT_BOUND_TO_SUDO_MONITOR") == 0);
}

static void test_origin_tty_mismatch_rejected(void) {
    aco_report report;
    valid_fixture(&report);
    report.nodes[2].stat.tty_nr = 34819;
    assert(aco_evaluate(&report) == ACO_CHAIN_MISMATCH);
}

static void test_origin_foreground_mismatch_rejected(void) {
    aco_report report;
    valid_fixture(&report);
    report.nodes[2].stat.tpgid = 202;
    assert(aco_evaluate(&report) == ACO_CHAIN_MISMATCH);
}

static void test_session_mismatch_rejected(void) {
    aco_report report;
    valid_fixture(&report);
    report.nodes[0].stat.session = 999;
    assert(aco_evaluate(&report) == ACO_CHAIN_MISMATCH);
}

static void test_missing_tty_is_incomplete(void) {
    aco_report report;
    valid_fixture(&report);
    report.tty_available = false;
    assert(aco_evaluate(&report) == ACO_CHAIN_INCOMPLETE);
}

static void test_missing_self_stat_is_incomplete(void) {
    aco_report report;
    valid_fixture(&report);
    report.self_stat_available = false;
    assert(aco_evaluate(&report) == ACO_CHAIN_INCOMPLETE);
}

static void test_self_tty_mismatch_rejected(void) {
    aco_report report;
    valid_fixture(&report);
    report.self_stat.tty_nr = 34819;
    assert(aco_evaluate(&report) == ACO_CHAIN_MISMATCH);
}

static void test_unstable_chain_is_incomplete(void) {
    aco_report report;
    valid_fixture(&report);
    report.chain_stable = false;
    assert(aco_evaluate(&report) == ACO_CHAIN_INCOMPLETE);
}

static void test_missing_pidfd_is_incomplete(void) {
    aco_report report;
    valid_fixture(&report);
    report.pidfds_stable = false;
    assert(aco_evaluate(&report) == ACO_CHAIN_INCOMPLETE);
}

static void test_node_without_pidfd_is_incomplete(void) {
    aco_report report;
    valid_fixture(&report);
    report.nodes[1].pidfd_open = false;
    assert(aco_evaluate(&report) == ACO_CHAIN_INCOMPLETE);
}

static void test_origin_uid_mismatch_rejected(void) {
    aco_report report;
    valid_fixture(&report);
    report.nodes[2].status.uid[0] = 2000U;
    assert(aco_evaluate(&report) == ACO_CHAIN_MISMATCH);
}

static void test_parent_link_mismatch_rejected(void) {
    aco_report report;
    valid_fixture(&report);
    report.nodes[0].stat.ppid = 555;
    assert(aco_evaluate(&report) == ACO_CHAIN_MISMATCH);
}

static void test_not_a_sudo_executable(void) {
    aco_node node = {0};
    set_exe(&node, "/tmp/sudo", (uint32_t)(S_IFREG | 0755));
    assert(!aco_is_sudo_candidate(&node));
    set_exe(&node, "/usr/bin/sudo", (uint32_t)(S_IFREG | S_ISUID | 0777));
    assert(!aco_is_sudo_candidate(&node));
    set_exe(&node, "/usr/bin/sudo", (uint32_t)(S_IFREG | S_ISUID | 0755));
    assert(aco_is_sudo_candidate(&node));
}

static void test_output_does_not_claim_authority(void) {
    aco_report report;
    FILE *stream = tmpfile();
    char output[4096];
    size_t count;

    assert(stream != NULL);
    valid_fixture(&report);
    (void)snprintf(report.nodes[2].exe_target,
                   sizeof(report.nodes[2].exe_target),
                   "/tmp/odd\nAUTHORIZATION=FORGED");
    (void)aco_evaluate(&report);
    aco_print_report(stream, &report);
    rewind(stream);
    count = fread(output, 1U, sizeof(output) - 1U, stream);
    output[count] = '\0';
    assert(strstr(output, "AUTHORIZATION=NOT_PROVIDED") != NULL);
    assert(strstr(output,
                  "chain[2].exe=/tmp/odd\\x0aAUTHORIZATION=FORGED") != NULL);
    assert(strstr(output, "\nAUTHORIZATION=FORGED\n") == NULL);
    assert(strstr(output, "AUTHORIZED") == NULL);
    assert(fclose(stream) == 0);
}

int main(void) {
    test_direct_sudo_pattern();
    test_shell_wrapper_rejected();
    test_bad_sudo_credentials_rejected();
    test_missing_origin_tty_rejected();
    test_origin_tty_mismatch_rejected();
    test_origin_foreground_mismatch_rejected();
    test_session_mismatch_rejected();
    test_missing_tty_is_incomplete();
    test_missing_self_stat_is_incomplete();
    test_self_tty_mismatch_rejected();
    test_unstable_chain_is_incomplete();
    test_missing_pidfd_is_incomplete();
    test_node_without_pidfd_is_incomplete();
    test_origin_uid_mismatch_rejected();
    test_parent_link_mismatch_rejected();
    test_not_a_sudo_executable();
    test_output_does_not_claim_authority();
    puts("bootstrap-chain-observer: tests passed");
    return 0;
}
