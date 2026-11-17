#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"

CC=${CC:-cc}
COMMON_FLAGS="-std=c11 -Wall -Wextra -Wpedantic -Werror"

$CC $COMMON_FLAGS -O2 \
  -o /tmp/atlas-bootstrap-validator-tests \
  tools/bootstrap-validator/bootstrap_validator.c \
  tools/bootstrap-validator/test_bootstrap_validator.c
/tmp/atlas-bootstrap-validator-tests

$CC $COMMON_FLAGS -O2 \
  -o /tmp/atlas-bootstrap-observer-tests \
  tools/bootstrap-validator/bootstrap_validator.c \
  tools/bootstrap-observer/bootstrap_observer_linux.c \
  tools/bootstrap-observer/test_bootstrap_observer_linux.c
/tmp/atlas-bootstrap-observer-tests

$CC $COMMON_FLAGS -O2 \
  -o /tmp/atlas-bootstrap-observer \
  tools/bootstrap-validator/bootstrap_validator.c \
  tools/bootstrap-observer/bootstrap_observer_linux.c \
  tools/bootstrap-observer/bootstrap_observer_main.c

if /tmp/atlas-bootstrap-observer --hold-ms 999 >/dev/null 2>&1; then
  printf '%s\n' "Invalid observer arguments were unexpectedly accepted." >&2
  exit 1
else
  status=$?
  if [ "$status" -ne 64 ]; then
    printf '%s\n' "Unexpected invalid-argument exit code: $status" >&2
    exit 1
  fi
fi

if /tmp/atlas-bootstrap-observer > /tmp/atlas-bootstrap-observer-smoke.txt 2>&1; then
  status=0
else
  status=$?
fi
case "$status" in
  0|2|3) ;;
  *)
    cat /tmp/atlas-bootstrap-observer-smoke.txt
    printf '%s\n' "Unexpected observer smoke-test exit code: $status" >&2
    exit 1
    ;;
esac
grep -qx 'AUTHORIZATION=NOT_PROVIDED' /tmp/atlas-bootstrap-observer-smoke.txt

printf '%s\n' "V2 build and automated tests completed."
printf '%s\n' "Observer binary: /tmp/atlas-bootstrap-observer"
