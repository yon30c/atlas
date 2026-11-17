#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"

CC=${CC:-cc}
FLAGS="-std=c11 -Wall -Wextra -Wpedantic -Werror -O2"
INCLUDES="-Itools/bootstrap-validator -Itools/bootstrap-chain-observer"

$CC $FLAGS $INCLUDES \
  -o /tmp/atlas-bootstrap-chain-tests \
  tools/bootstrap-validator/bootstrap_validator.c \
  tools/bootstrap-chain-observer/bootstrap_chain_observer.c \
  tools/bootstrap-chain-observer/test_bootstrap_chain_observer.c
/tmp/atlas-bootstrap-chain-tests

$CC $FLAGS $INCLUDES \
  -o /tmp/atlas-bootstrap-chain-observer \
  tools/bootstrap-validator/bootstrap_validator.c \
  tools/bootstrap-chain-observer/bootstrap_chain_observer.c \
  tools/bootstrap-chain-observer/bootstrap_chain_observer_main.c

if /tmp/atlas-bootstrap-chain-observer > /tmp/atlas-bootstrap-chain-smoke.txt 2>&1; then
  status=0
else
  status=$?
fi
case "$status" in
  0|2|3) ;;
  *)
    cat /tmp/atlas-bootstrap-chain-smoke.txt
    printf '%s\n' "Unexpected chain observer smoke exit: $status" >&2
    exit 1
    ;;
esac
grep -qx 'AUTHORIZATION=NOT_PROVIDED' /tmp/atlas-bootstrap-chain-smoke.txt

printf '%s\n' "Bootstrap chain observer build and tests completed."
printf '%s\n' "Observer binary: /tmp/atlas-bootstrap-chain-observer"
