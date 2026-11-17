#include "bootstrap_validator.h"

#include <limits.h>
#include <string.h>

static bool u64(const unsigned char *s, size_t n, uint64_t max, uint64_t *out) {
    uint64_t v = 0;

    if (!n) {
        return false;
    }

    for (size_t i = 0; i < n; i++) {
        unsigned d;

        if (s[i] < '0' || s[i] > '9') {
            return false;
        }
        d = (unsigned)(s[i] - '0');

        if ((uint64_t)d > max || v > (max - d) / 10U) {
            return false;
        }
        v = v * 10U + d;
    }

    *out = v;
    return true;
}

static bool i64(const unsigned char *s, size_t n, int64_t min, int64_t max,
                int64_t *out) {
    bool neg = false;
    uint64_t mag;
    uint64_t limit;

    if (!n) {
        return false;
    }
    if (*s == '-') {
        neg = true;
        s++;
        n--;
    } else if (*s == '+') {
        return false;
    }
    if (!n) {
        return false;
    }

    limit = neg ? (uint64_t)(-(min + 1)) + 1U : (uint64_t)max;
    if (!u64(s, n, limit, &mag)) {
        return false;
    }

    if (neg) {
        if (mag == (uint64_t)INT64_MAX + 1U) {
            *out = INT64_MIN;
        } else {
            *out = -(int64_t)mag;
        }
    } else {
        *out = (int64_t)mag;
    }

    return *out >= min && *out <= max;
}

static bool pidnum(const unsigned char *s, size_t n, int32_t *out) {
    uint64_t v;

    if (!u64(s, n, ATLAS_PID_MAX, &v)) {
        return false;
    }
    *out = (int32_t)v;
    return true;
}

static bool buffer_ok(const unsigned char *d, size_t n, size_t max) {
    if (!d || !n || n > max) {
        return false;
    }

    for (size_t i = 0; i < n; i++) {
        if (d[i] == 0) {
            return false;
        }
    }
    return true;
}

bv_parse_result bv_parse_status(const unsigned char *d, size_t n,
                                bv_status *out) {
    bv_status v = {0};
    bool hp = false;
    bool hu = false;
    bool hg = false;
    size_t p = 0;

    if (!d || !out || !n) {
        return BV_INVALID;
    }
    if (n > ATLAS_PROC_STATUS_MAX) {
        return BV_TOO_LARGE;
    }
    if (!buffer_ok(d, n, ATLAS_PROC_STATUS_MAX)) {
        return BV_INVALID;
    }

    while (p < n) {
        size_t e = p;
        size_t c;
        size_t vs;

        while (e < n && d[e] != '\n') {
            e++;
        }
        if (e == p) {
            return BV_INVALID;
        }

        c = p;
        while (c < e && d[c] != ':') {
            c++;
        }

        if (c < e) {
            vs = c + 1;
            while (vs < e && (d[vs] == ' ' || d[vs] == '\t')) {
                vs++;
            }

            if (c - p == 4 && memcmp(d + p, "PPid", 4) == 0) {
                if (hp) {
                    return BV_DUPLICATE;
                }
                if (!pidnum(d + vs, e - vs, &v.ppid)) {
                    return BV_INVALID;
                }
                hp = true;
            } else if ((c - p == 3 && memcmp(d + p, "Uid", 3) == 0) ||
                       (c - p == 3 && memcmp(d + p, "Gid", 3) == 0)) {
                bool isuid = d[p] == 'U';
                bool *seen = isuid ? &hu : &hg;
                uint32_t *a = isuid ? v.uid : v.gid;
                size_t q = vs;

                if (*seen) {
                    return BV_DUPLICATE;
                }

                for (size_t i = 0; i < 4; i++) {
                    size_t st = q;
                    uint64_t x;

                    while (q < e && d[q] >= '0' && d[q] <= '9') {
                        q++;
                    }
                    if (q == st) {
                        return BV_INVALID;
                    }
                    if (!u64(d + st, q - st, UINT32_MAX, &x)) {
                        return BV_RANGE;
                    }
                    a[i] = (uint32_t)x;

                    if (i < 3) {
                        if (q >= e || (d[q] != ' ' && d[q] != '\t')) {
                            return BV_INVALID;
                        }
                        while (q < e && (d[q] == ' ' || d[q] == '\t')) {
                            q++;
                        }
                    }
                }

                if (q != e) {
                    return BV_INVALID;
                }
                *seen = true;
            }
        }

        p = e < n ? e + 1 : e;
    }

    if (!hp || !hu || !hg) {
        return BV_MISSING;
    }
    *out = v;
    return BV_OK;
}

bv_parse_result bv_parse_stat(const unsigned char *d, size_t n,
                              int32_t expected, bv_stat *out) {
    bv_stat v = {0};
    size_t first = 0;
    size_t close;
    size_t p;
    size_t end;
    int32_t parsed_pid;
    int64_t sv;
    uint64_t uv;

    if (!d || !out || !n || expected <= 0) {
        return BV_INVALID;
    }
    if (n > ATLAS_PROC_STAT_MAX) {
        return BV_TOO_LARGE;
    }
    if (!buffer_ok(d, n, ATLAS_PROC_STAT_MAX)) {
        return BV_INVALID;
    }

    end = n;
    if (d[end - 1] == '\n') {
        end--;
    }
    if (end == 0) {
        return BV_INVALID;
    }
    for (size_t i = 0; i < end; i++) {
        if (d[i] == '\n' || d[i] == '\r' || d[i] == '\t' ||
            d[i] == '\v' || d[i] == '\f') {
            return BV_INVALID;
        }
    }

    while (first < end && d[first] != ' ') {
        first++;
    }
    if (first == end || !pidnum(d, first, &parsed_pid) ||
        parsed_pid != expected || first + 1 >= end || d[first + 1] != '(') {
        return BV_INVALID;
    }

    close = end;
    while (close > first + 2 && d[close - 1] != ')') {
        close--;
    }
    if (close <= first + 2) {
        return BV_INVALID;
    }
    --close;

    p = close + 1;
    if (p >= end || d[p] != ' ') {
        return BV_INVALID;
    }
    while (p < end && d[p] == ' ') {
        p++;
    }

    for (unsigned field = 3; field <= 22; field++) {
        size_t st = p;
        size_t e;

        while (p < end && d[p] != ' ') {
            p++;
        }
        e = p;
        if (st == e) {
            return BV_TRUNCATED;
        }

        if (field == 3) {
            if (e - st != 1 || !strchr("RSDZTWtXxKWPI", d[st])) {
                return BV_INVALID;
            }
            v.state = (char)d[st];
        } else if (field >= 4 && field <= 6) {
            int32_t *dst = field == 4 ? &v.ppid
                            : field == 5 ? &v.pgrp
                                         : &v.session;
            if (!pidnum(d + st, e - st, dst)) {
                return BV_RANGE;
            }
        } else if (field == 7 || field == 8) {
            if (!i64(d + st, e - st, INT32_MIN, INT32_MAX, &sv)) {
                return BV_RANGE;
            }
            if (field == 7) {
                v.tty_nr = sv;
            } else {
                v.tpgid = (int32_t)sv;
            }
        } else if ((field >= 9 && field <= 15) || field == 22) {
            if (!u64(d + st, e - st, UINT64_MAX, &uv)) {
                return BV_RANGE;
            }
            if (field == 22) {
                v.starttime = uv;
            }
        } else if (!i64(d + st, e - st, INT64_MIN, INT64_MAX, &sv)) {
            return BV_INVALID;
        }

        while (p < end && d[p] == ' ') {
            p++;
        }
    }

    if (p < end) {
        return BV_INVALID;
    }
    v.pid = parsed_pid;
    *out = v;
    return BV_OK;
}

bv_observation_result bv_evaluate(const bv_observation *o,
                                  const bv_fixture_policy *p) {
    if (!o || !p || !o->has_requested_pid || !o->has_helper_pid ||
        !o->has_helper_parent_pid || !o->has_parent_status ||
        !o->has_parent_stat || !o->has_parent_starttime_first ||
        !o->has_parent_starttime_second ||
        o->parent_pidfd == BV_PIDFD_NOT_REQUESTED) {
        return BV_OBSERVATION_INCOMPLETE;
    }

    if (o->requested_pid <= 0 || o->helper_pid <= 0 ||
        o->helper_parent_pid <= 0 || o->requested_pid != o->helper_parent_pid ||
        o->parent_stat.pid != o->requested_pid ||
        o->parent_status.ppid != o->parent_stat.ppid ||
        o->parent_starttime_first != o->parent_starttime_second ||
        o->parent_stat.starttime != o->parent_starttime_first) {
        return BV_OBSERVATION_INCONSISTENT;
    }

    if (o->parent_pidfd != BV_PIDFD_OPEN_UNSIGNALED) {
        return BV_OBSERVATION_INCONSISTENT;
    }
    if (p->enforce_parent_uid &&
        o->parent_status.uid[0] != p->expected_parent_uid) {
        return BV_OBSERVATION_INCONSISTENT;
    }
    if (p->enforce_parent_gid &&
        o->parent_status.gid[0] != p->expected_parent_gid) {
        return BV_OBSERVATION_INCONSISTENT;
    }
    if (o->has_tty_relations &&
        (o->terminal_sid != o->process_sid ||
         o->process_pgrp != o->foreground_pgrp)) {
        return BV_OBSERVATION_INCONSISTENT;
    }

    return BV_OBSERVATION_CONSISTENT;
}
