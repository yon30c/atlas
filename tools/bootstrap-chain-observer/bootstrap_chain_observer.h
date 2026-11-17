#ifndef ATLAS_BOOTSTRAP_CHAIN_OBSERVER_H
#define ATLAS_BOOTSTRAP_CHAIN_OBSERVER_H

#include "bootstrap_validator.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/types.h>

#define ACO_MAX_NODES 8U
#define ACO_EXE_TARGET_MAX 512U

typedef enum {
    ACO_PATTERN_MATCHED_DIAGNOSTICALLY = 0,
    ACO_CHAIN_MISMATCH,
    ACO_CHAIN_INCOMPLETE
} aco_result;

typedef struct {
    pid_t pid;
    bv_status status;
    bv_stat stat;
    bool have_status;
    bool have_stat;
    bool have_exe;
    bool pidfd_open;
    uint64_t exe_device;
    uint64_t exe_inode;
    uint32_t exe_mode;
    uint32_t exe_uid;
    uint32_t exe_gid;
    char exe_target[ACO_EXE_TARGET_MAX];
} aco_node;

typedef struct {
    pid_t self_pid;
    pid_t self_parent_pid;
    int32_t self_sid;
    int32_t self_pgrp;
    bool self_stat_available;
    bv_stat self_stat;
    bool tty_available;
    int tty_errno;
    int32_t terminal_sid;
    int32_t foreground_pgrp;
    bool chain_stable;
    bool pidfds_stable;
    bool collection_complete;
    size_t node_count;
    aco_node nodes[ACO_MAX_NODES];
    size_t sudo_count;
    size_t origin_index;
    aco_result result;
    const char *reason;
} aco_report;

bool aco_is_sudo_candidate(const aco_node *node);
bool aco_node_equal(const aco_node *left, const aco_node *right);
aco_result aco_evaluate(aco_report *report);
int aco_collect(aco_report *report);
void aco_print_report(FILE *stream, const aco_report *report);

#endif
