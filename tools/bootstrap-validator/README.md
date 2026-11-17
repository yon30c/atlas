# Bootstrap validator V1 (unprivileged, fixture-only)

This component contains pure parsers and a consistency evaluator for synthetic
Linux proc fixtures. It is independent from tools/bootstrap-probe.

## Strict boundary

- No process collector and no live procfs reads.
- No pidfd, TTY, executable, sudo, SSH, PAM, keys, protected configuration,
  SQLite, CAM, Broker, network, or runtime integration.
- Evaluator outputs are limited to OBSERVATION_CONSISTENT,
  OBSERVATION_INCONSISTENT, and OBSERVATION_INCOMPLETE.
- A consistent fixture is not evidence that a real process or invocation is
  trusted.
- No privileges, setuid bit, file capabilities, package installation, or host
  configuration changes.
- pidfd and TTY values are synthetic fixture inputs, not syscall results.

## Build and run tests

From the repository root on Debian:

```sh
cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  -o /tmp/atlas-bootstrap-validator-tests \
  tools/bootstrap-validator/bootstrap_validator.c \
  tools/bootstrap-validator/test_bootstrap_validator.c
/tmp/atlas-bootstrap-validator-tests
```

Expected output: bootstrap-validator V1: tests passed

The executable belongs in /tmp. Do not install it or run it through sudo.

## Interface

bootstrap_validator.h exposes length-delimited parsers for proc status and
stat, plus a pure evaluator over caller-supplied observations. Parser outputs
are written only after successful parsing.
