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

int main(void) {
    test_hold_arguments();
    puts("bootstrap-observer V2: unit tests passed");
    return 0;
}
