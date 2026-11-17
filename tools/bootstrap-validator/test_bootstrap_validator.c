#include "bootstrap_validator.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static const unsigned char status_ok[]="Name:\ttest\nState:\tR (running)\nGid:\t0\t0\t0\t0\nPPid:\t123\nUid:\t1000\t1000\t1000\t1000\n";
static const unsigned char stat_ok[]="123 (sudo (worker)) S 10 11 12 34818 13 0 1 2 3 4 5 6 7 8 9 10 11 12 987654\n";
static void test_status(void){
 bv_status o; assert(bv_parse_status(status_ok,sizeof(status_ok)-1,&o)==BV_OK); assert(o.ppid==123&&o.uid[3]==1000&&o.gid[3]==0);
 const char *m="PPid: 1\nUid: 1 1 1 1\n"; assert(bv_parse_status((const unsigned char*)m,strlen(m),&o)==BV_MISSING);
 const char *d="PPid: 1\nPPid: 2\nUid: 1 1 1 1\nGid: 1 1 1 1\n"; assert(bv_parse_status((const unsigned char*)d,strlen(d),&o)==BV_DUPLICATE);
 const char *bad="PPid: 1\nUid: 1 2 -3 4\nGid: 1 1 1 1\n"; assert(bv_parse_status((const unsigned char*)bad,strlen(bad),&o)!=BV_OK);
 const char *extra="PPid: 1\nUid: 1 2 3 4 5\nGid: 1 1 1 1\n"; assert(bv_parse_status((const unsigned char*)extra,strlen(extra),&o)==BV_INVALID);
 const unsigned char nul[]={'P','P','i','d',':',' ','1',0,'\n'}; assert(bv_parse_status(nul,sizeof(nul),&o)==BV_INVALID);
 assert(bv_parse_status(status_ok,0,&o)==BV_INVALID);
}
static void test_stat(void){
 bv_stat o; assert(bv_parse_stat(stat_ok,sizeof(stat_ok)-1,123,&o)==BV_OK);
 assert(o.pid==123&&o.ppid==10&&o.pgrp==11&&o.session==12&&o.tty_nr==34818&&o.tpgid==13&&o.starttime==987654);
 assert(bv_parse_stat(stat_ok,sizeof(stat_ok)-1,124,&o)==BV_INVALID);
 const char *shortline="123 (x) S 10 11 12 0 0"; assert(bv_parse_stat((const unsigned char*)shortline,strlen(shortline),123,&o)==BV_TRUNCATED);
 const char *bad="123 (x) S 10 11 12 0 0 0 0 0 0 0 0 0 0 0 0 0 0 nope"; assert(bv_parse_stat((const unsigned char*)bad,strlen(bad),123,&o)!=BV_OK);
 const char *tail="123 (x) S 10 11 12 0 0 0 0 0 0 0 0 0 0 0 0 0 0 10 extra"; assert(bv_parse_stat((const unsigned char*)tail,strlen(tail),123,&o)==BV_INVALID);
}
static bv_observation complete(void){
 bv_observation o={0}; o.has_requested_pid=true;o.requested_pid=123;o.has_helper_pid=true;o.helper_pid=200;
 o.has_helper_parent_pid=true;o.helper_parent_pid=123;o.has_parent_status=true;o.parent_status.ppid=10;
 o.parent_status.uid[0]=1000;o.parent_status.gid[0]=0;o.has_parent_stat=true;o.parent_stat.pid=123;
 o.parent_stat.ppid=10;o.parent_stat.starttime=555;o.has_parent_starttime_first=true;o.parent_starttime_first=555;
 o.has_parent_starttime_second=true;o.parent_starttime_second=555;o.parent_pidfd=BV_PIDFD_OPEN_UNSIGNALED;return o;
}
static void test_evaluator(void){
 bv_fixture_policy p={0};bv_observation o=complete();assert(bv_evaluate(&o,&p)==BV_OBSERVATION_CONSISTENT);
 o.parent_stat.ppid=11;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.parent_starttime_second++;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.parent_pidfd=BV_PIDFD_SIGNALED;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.has_tty_relations=true;o.terminal_sid=1;o.process_sid=2;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();p.enforce_parent_uid=true;p.expected_parent_uid=0;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCONSISTENT);
 o=complete();o.has_parent_stat=false;assert(bv_evaluate(&o,&p)==BV_OBSERVATION_INCOMPLETE);
}
int main(void){test_status();test_stat();test_evaluator();puts("bootstrap-validator V1: tests passed");return 0;}
