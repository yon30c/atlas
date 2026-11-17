#ifndef ATLAS_BOOTSTRAP_OBSERVER_LINUX_H
#define ATLAS_BOOTSTRAP_OBSERVER_LINUX_H

#include "bootstrap_validator.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/types.h>

typedef struct {
    bv_observation_result result;
    pid_t self_pid;
    pid_t parent_pid;
    bool have_self_stat;
    bv_stat self_stat;
    bool have_parent_first;
    bool have_parent_second;
    bv_status parent_status_first;
    bv_status parent_status_second;
    bv_stat parent_stat_first;
    bv_stat parent_stat_second;
    bv_parse_result status_parse_first;
    bv_parse_result status_parse_second;
    bv_parse_result stat_parse_first;
    bv_parse_result stat_parse_second;
    bv_pidfd_state pidfd_state;
    int pidfd_errno;
    bool parent_stable;
    bool exe_first_available;
    bool exe_second_available;
    bool exe_stable;
    uint64_t exe_device;
    uint64_t exe_inode;
    uint32_t exe_mode;
    uint32_t exe_uid;
    uint32_t exe_gid;
    char exe_target[512];
    bool tty_available;
    int tty_errno;
    int32_t terminal_sid;
    int32_t process_sid;
    int32_t process_pgrp;
    int32_t foreground_pgrp;
    bool tty_changed;
} bo_report;

int bo_collect(bo_report *report);
bool bo_parse_hold_ms(const char *value, unsigned *milliseconds);
int bo_run_hold(bo_report *report, unsigned milliseconds);
void bo_print_report(FILE *stream, const bo_report *report);

#endif
