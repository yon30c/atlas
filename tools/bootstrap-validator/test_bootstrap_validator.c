#include "bootstrap_validator.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static const unsigned char status_ok[]="Name:\ttest\nState:\tR (running)\nGid:\t0\t0\t0\t0\nPPid:\t123\nUid:\t1000\t1000\t1000\t1000\n";
static const unsigned char stat_ok[]="123 (sudo (worker)) S 10 11 12 34818 13 0 1 2 3 4 5 6 7 8 9 10 11 12 987654\n";
static const unsigned char stat_linux_full[]="2320 (bash) S 2319 2320 2320 34816 12667 4194304 47459 3181189 0 764 37 54 41920 3026 20 0 1 0 3539 9461760 1496 18446744073709551615 94168313634816 94168314457953 140736152141424 0 0 0 65536 3686404 1266761467 1 0 0 17 3 0 0 0 0 0 94168314690128 94168314738532 94169368309760 140736152145482 140736152145488 140736152145488 140736152145902 0\n";
static void test_status(void){
 bv_status o;
 assert(bv_parse_status(status_ok,sizeof(status_ok)-1,&o)==BV_OK);
 assert(o.ppid==123&&o.uid[3]==1000&&o.gid[3]==0);
 const char *ordered="Gid:\t7 7 7 7\nName:\tx\nUid:\t8 8 8 8\nPPid:\t9";
 assert(bv_parse_status((const unsigned char*)ordered,strlen(ordered),&o)==BV_OK);
 assert(o.ppid==9&&o.uid[0]==8&&o.gid[0]==7);
 const char *missing_ppid="Uid: 1 1 1 1\nGid: 1 1 1 1\n";
 const char *missing_uid="PPid: 1\nGid: 1 1 1 1\n";
 const char *missing_gid="PPid: 1\nUid: 1 1 1 1\n";
 assert(bv_parse_status((const unsigned char*)missing_ppid,strlen(missing_ppid),&o)==BV_MISSING);
 assert(bv_parse_status((const unsigned char*)missing_uid,strlen(missing_uid),&o)==BV_MISSING);
 assert(bv_parse_status((const unsigned char*)missing_gid,strlen(missing_gid),&o)==BV_MISSING);
 const char *dup_ppid="PPid: 1\nPPid: 2\nUid: 1 1 1 1\nGid: 1 1 1 1\n";
 const char *dup_uid="PPid: 1\nUid: 1 1 1 1\nUid: 2 2 2 2\nGid: 1 1 1 1\n";
 const char *dup_gid="PPid: 1\nUid: 1 1 1 1\nGid: 1 1 1 1\nGid: 2 2 2 2\n";
 assert(bv_parse_status((const unsigned char*)dup_ppid,strlen(dup_ppid),&o)==BV_DUPLICATE);
 assert(bv_parse_status((const unsigned char*)dup_uid,strlen(dup_uid),&o)==BV_DUPLICATE);
 assert(bv_parse_status((const unsigned char*)dup_gid,strlen(dup_gid),&o)==BV_DUPLICATE);
 const char *negative="PPid: -1\nUid: 1 1 1 1\nGid: 1 1 1 1\n";
 const char *overflow="PPid: 1\nUid: 4294967296 1 1 1\nGid: 1 1 1 1\n";
 const char *extra="PPid: 1\nUid: 1 2 3 4 5\nGid: 1 1 1 1\n";
 assert(bv_parse_status((const unsigned char*)negative,strlen(negative),&o)!=BV_OK);
 assert(bv_parse_status((const unsigned char*)overflow,strlen(overflow),&o)==BV_RANGE);
 assert(bv_parse_status((const unsigned char*)extra,strlen(extra),&o)==BV_INVALID);
 const unsigned char nul[]={'P','P','i','d',':',' ','1',0,'\n'};
 assert(bv_parse_status(nul,sizeof(nul),&o)==BV_INVALID);
 assert(bv_parse_status(status_ok,0,&o)==BV_INVALID);
 assert(bv_parse_status(status_ok,sizeof(status_ok)-1,&o)==BV_OK);
 unsigned char oversized[ATLAS_PROC_STATUS_MAX+1U]={0};
 assert(bv_parse_status(oversized,sizeof(oversized),&o)==BV_TOO_LARGE);
}
static void test_stat(void){
 bv_stat o;
 assert(bv_parse_stat(stat_ok,sizeof(stat_ok)-1,123,&o)==BV_OK);
 assert(o.pid==123&&o.ppid==10&&o.pgrp==11&&o.session==12&&o.tty_nr==34818&&o.tpgid==13&&o.starttime==987654);
 assert(bv_parse_stat(stat_linux_full,sizeof(stat_linux_full)-1,2320,&o)==BV_OK);
 assert(o.pid==2320&&o.ppid==2319&&o.pgrp==2320&&o.session==2320&&o.tty_nr==34816&&o.tpgid==12667&&o.starttime==3539);
 assert(bv_parse_stat(stat_ok,sizeof(stat_ok)-1,124,&o)==BV_INVALID);
 const char *shortline="123 (x) S 10 11 12 0 0";
 const char *missing_start="123 (x) S 10 11 12 0 0 0 1 2 3 4 5 6 -7 -8 -9 -10 11 -12";
 const char *bad_state="123 (x) Q 10 11 12 0 0 0 1 2 3 4 5 6 -7 -8 -9 -10 11 -12 987654";
 const char *bad="123 (x) S 10 11 12 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 nope";
 const char *tail="123 (x) S 10 11 12 0 0 0 0 0 0 0 0 0 0 0 0 0 0 10 11 extra";
 assert(bv_parse_stat((const unsigned char*)shortline,strlen(shortline),123,&o)==BV_TRUNCATED);
 assert(bv_parse_stat((const unsigned char*)missing_start,strlen(missing_start),123,&o)==BV_TRUNCATED);
 assert(bv_parse_stat((const unsigned char*)bad_state,strlen(bad_state),123,&o)==BV_INVALID);
 assert(bv_parse_stat((const unsigned char*)bad,strlen(bad),123,&o)!=BV_OK);
 assert(bv_parse_stat((const unsigned char*)tail,strlen(tail),123,&o)==BV_INVALID);
 const char *unsigned_counter="123 (x) S 10 11 12 0 0 18446744073709551615 1 2 3 4 5 6 -7 -8 -9 -10 11 -12 987654";
 const char *negative_counter="123 (x) S 10 11 12 0 0 -1 1 2 3 4 5 6 -7 -8 -9 -10 11 -12 987654";
 const char *overflow_start="123 (x) S 10 11 12 0 0 0 1 2 3 4 5 6 -7 -8 -9 -10 11 -12 18446744073709551616";
 assert(bv_parse_stat((const unsigned char*)unsigned_counter,strlen(unsigned_counter),123,&o)==BV_OK);
 assert(bv_parse_stat((const unsigned char*)negative_counter,strlen(negative_counter),123,&o)==BV_RANGE);
 assert(bv_parse_stat((const unsigned char*)overflow_start,strlen(overflow_start),123,&o)==BV_RANGE);
 const char *crlf="123 (x) S 10 11 12 0 0 0 1 2 3 4 5 6 -7 -8 -9 -10 11 -12 987654\r\n";
 const char *split="123 (x) S 10 11 12 0 0 0 1 2 3 4 5 6 -7 -8 -9 -10 11 -12\n987654";
 const char *tab="123 (x)\tS 10 11 12 0 0 0 1 2 3 4 5 6 -7 -8 -9 -10 11 -12 987654";
 assert(bv_parse_stat((const unsigned char*)crlf,strlen(crlf),123,&o)==BV_INVALID);
 assert(bv_parse_stat((const unsigned char*)split,strlen(split),123,&o)==BV_INVALID);
 assert(bv_parse_stat((const unsigned char*)tab,strlen(tab),123,&o)==BV_INVALID);
 unsigned char oversized[ATLAS_PROC_STAT_MAX+1U]={0};
 assert(bv_parse_stat(oversized,sizeof(oversized),123,&o)==BV_TOO_LARGE);
}
static bv_observation complete(void){
 bv_observation o={0}; o.has_requested_pid=true;o.requested_pid=123;o.has_helper_pid=true;o.helper_pid=200;
 o.has_helper_parent_pid=true;o.helper_parent_pid=123;o.has_parent_status=true;o.parent_status.ppid=10;
 o.parent_status.uid[0]=1000;o.parent_status.gid[0]=0;o.has_parent_stat=true;o.parent_stat.pid=123;
 o.parent_stat.ppid=10;o.parent_stat.starttime=555;o.has_parent_starttime_first=true;o.parent_starttime_first=555;
 o.has_parent_starttime_second=true;o.parent_starttime_second=555;o.parent_pidfd=BV_PIDFD_OPEN_UNSIGNALED;return o;
}
static void test_evaluator(void){
 bv_fixture_policy p={0};
 bv_observation o=complete();
 assert(bv_evaluate(&o,&p)==BV_OBSERVATION_CONSISTENT);
 o.parent_stat.ppid=11;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.helper_pid=o.requested_pid;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.helper_parent_pid++;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.parent_status.ppid++;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.parent_starttime_second++;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.parent_stat.starttime++;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.parent_pidfd=BV_PIDFD_SIGNALED;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.parent_pidfd=BV_PIDFD_ERROR;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.parent_pidfd=BV_PIDFD_NOT_REQUESTED;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCOMPLETE);
 o=complete();p.enforce_parent_uid=true;p.expected_parent_uid=0;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();p.enforce_parent_uid=false;p.enforce_parent_gid=true;p.expected_parent_gid=5;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();p.enforce_parent_gid=false;o.has_tty_relations=true;o.terminal_sid=1;o.process_sid=2;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.has_tty_relations=true;o.terminal_sid=1;o.process_sid=1;o.process_pgrp=2;o.foreground_pgrp=3;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.has_requested_pid=false;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCOMPLETE);
 o=complete();o.has_helper_pid=false;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCOMPLETE);
 o=complete();o.has_helper_parent_pid=false;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCOMPLETE);
 o=complete();o.has_parent_status=false;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCOMPLETE);
 o=complete();o.has_parent_stat=false;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCOMPLETE);
 o=complete();o.has_parent_starttime_first=false;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCOMPLETE);
 o=complete();o.has_parent_starttime_second=false;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCOMPLETE);
}
int main(void){test_status();test_stat();test_evaluator();puts("bootstrap-validator V1: tests passed");return 0;}
