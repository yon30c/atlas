#ifndef ATLAS_BOOTSTRAP_VALIDATOR_H
#define ATLAS_BOOTSTRAP_VALIDATOR_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define ATLAS_PROC_STATUS_MAX 65536U
#define ATLAS_PROC_STAT_MAX 8192U
#define ATLAS_PID_MAX INT32_MAX
typedef enum { BV_OK=0, BV_INVALID, BV_TRUNCATED, BV_MISSING, BV_DUPLICATE, BV_RANGE, BV_TOO_LARGE } bv_parse_result;
typedef struct { int32_t ppid; uint32_t uid[4]; uint32_t gid[4]; } bv_status;
typedef struct { int32_t pid; char state; int32_t ppid; int32_t pgrp; int32_t session; int64_t tty_nr; int32_t tpgid; uint64_t starttime; } bv_stat;
typedef enum { BV_OBSERVATION_CONSISTENT=0, BV_OBSERVATION_INCONSISTENT, BV_OBSERVATION_INCOMPLETE } bv_observation_result;
typedef enum { BV_PIDFD_NOT_REQUESTED=0, BV_PIDFD_OPEN_UNSIGNALED, BV_PIDFD_SIGNALED, BV_PIDFD_ERROR } bv_pidfd_state;
typedef struct {
 bool has_requested_pid; int32_t requested_pid;
 bool has_helper_pid; int32_t helper_pid;
 bool has_helper_parent_pid; int32_t helper_parent_pid;
 bool has_parent_status; bv_status parent_status;
 bool has_parent_stat; bv_stat parent_stat;
 bool has_parent_starttime_first; uint64_t parent_starttime_first;
 bool has_parent_starttime_second; uint64_t parent_starttime_second;
 bv_pidfd_state parent_pidfd;
 bool has_tty_relations; int32_t terminal_sid; int32_t process_sid;
 int32_t process_pgrp; int32_t foreground_pgrp;
} bv_observation;
typedef struct { bool enforce_parent_uid; uint32_t expected_parent_uid; bool enforce_parent_gid; uint32_t expected_parent_gid; } bv_fixture_policy;
bv_parse_result bv_parse_status(const unsigned char *data,size_t length,bv_status *out);
bv_parse_result bv_parse_stat(const unsigned char *data,size_t length,int32_t expected_pid,bv_stat *out);
bv_observation_result bv_evaluate(const bv_observation *observation,const bv_fixture_policy *policy);
#endif
