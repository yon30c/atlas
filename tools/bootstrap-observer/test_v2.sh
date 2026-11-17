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

printf '%s\n' "V2 build and automated tests completed."
printf '%s\n' "Observer binary: /tmp/atlas-bootstrap-observer"
