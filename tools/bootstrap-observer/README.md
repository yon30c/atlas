# Bootstrap observer V2 (Linux, read-only)

V2 is a separate Linux adapter around the pure V1 parser/evaluator. It observes
the current process, its direct parent, procfs snapshots, pidfd state,
executable metadata and the controlling TTY when available.

## Safety boundary

- Read-only procfs access, pidfd open/poll, executable metadata via O_PATH and
  fstat, and TTY queries only.
- No shell-outs, no network, no filesystem or host writes, no PAM, no keys, no protected config,
  no sudo API, no systemd/SSH/Broker/SQLite/CAM/runtime integration.
- The program never invokes sudo or asks for privileges.
- Running the diagnostic manually through sudo is an optional test scenario,
  not an authorization flow.
- No executable path, inode, process name, UID, TTY owner or PTY is treated as
  proof that the parent is sudo or that a person is present.
- No output is ALLOW, AUTHORIZED, TRUSTED or PROOF_READY.
- Build and run only from the checkout and /tmp. Do not install the binary.

A consistent result means only that the bounded observations available to this
program did not contradict the limited V1 rules during this sample. procfs
reads are not atomic and a process may change immediately after observation.
Executable target text is escaped before printing so control characters cannot
forge additional report lines.

## Build and run automated tests

From the repository root on Debian:

```sh
sh tools/bootstrap-observer/test_v2.sh
```

The script builds with `-std=c11 -Wall -Wextra -Wpedantic -Werror`, runs
the V1 parser suite, runs the V2 classification/snapshot tests and a live
collector smoke test, builds the observer CLI, checks invalid arguments and runs a CLI smoke test. All binaries are placed in
`/tmp`.

Expected output:

- `bootstrap-validator V1: tests passed`
- `bootstrap-observer V2: unit and live smoke tests passed`
- `V2 build and automated tests completed.`

## Manual Debian observations

Run these only after the automated build succeeds:

```sh
/tmp/atlas-bootstrap-observer
printf 'exit=%s\n' "$?"

/tmp/atlas-bootstrap-observer --hold-ms 5000
printf 'exit=%s\n' "$?"
```

To observe a foreground change using interactive shell job control, run this
in a terminal with job control enabled:

```sh
/tmp/atlas-bootstrap-observer --hold-ms 10000 &
sleep 1
fg %1
```

The observer begins in the background and should detect the foreground process
group changing when the shell brings it to the foreground. This is a
diagnostic exercise only; it does not authenticate the terminal or operator.

Exit codes:

- 0: observations complete and consistent under V1's limited rules;
- 2: incomplete observation when required evidence is unavailable and no
  independent contradiction was observed;
- 3: an observed contradiction or a process/TTY/executable change. A
  contradiction takes precedence over missing evidence;
- 1: internal/system error;
- 64: invalid command-line arguments.

Without a controlling TTY, the observer will normally be incomplete (exit 2)
if the other observations do not contradict the limited rules. It can return
inconsistent (exit 3) when an independent contradiction is also observed. For
example, in the tested SSH-without-PTY case the direct parent and observer
belonged to different sessions, so the session mismatch took precedence over
the unavailable TTY. This is an expected fail-closed result, not a reason to
weaken the checks.

Optional manual scenarios, chosen and run by the operator:

```sh
# Ordinary local terminal
/tmp/atlas-bootstrap-observer

# Direct sudo from a local terminal
sudo -- /tmp/atlas-bootstrap-observer

# SSH with PTY, direct sudo invocation (from the Windows client)
ssh -t greed@10.0.0.81 'sudo -- /tmp/atlas-bootstrap-observer'

# SSH with PTY and an intermediate shell; direct parent should be the shell
ssh -t greed@10.0.0.81 'sudo -- sh -c "/tmp/atlas-bootstrap-observer"'

# SSH without PTY, ordinary unprivileged observation.
# TTY absence alone is incomplete; an independent session mismatch is inconsistent.
ssh -T greed@10.0.0.81 '/tmp/atlas-bootstrap-observer'
```

Do not use `sudo -S`, do not enable NOPASSWD, do not change sudo timestamp
policy, sudoers, SSH, PAM, systemd or host configuration. If sudo refuses to
run without a terminal, that scenario is inconclusive; do not work around it.

## Sanitizers

If the installed compiler supports them:

```sh
cc -std=c11 -O1 -g -Wall -Wextra -Wpedantic -Werror \
  -Itools/bootstrap-validator -fsanitize=address,undefined -fno-omit-frame-pointer \
  -o /tmp/atlas-bootstrap-observer-sanitized \
  tools/bootstrap-validator/bootstrap_validator.c \
  tools/bootstrap-observer/bootstrap_observer_linux.c \
  tools/bootstrap-observer/test_bootstrap_observer_linux.c

/tmp/atlas-bootstrap-observer-sanitized
```

## Interpretation

The observer captures a direct-parent relationship and bounded double samples.
A pidfd pins a process reference but does not freeze PPID, credentials, exec,
session, process group or TTY state. An O_PATH descriptor and fstat describe
the executable object opened at that moment; they do not prevent a later
execve. A PTY does not reveal whether it originated from SSH, a local terminal
or sudo's use_pty behavior.

V2 does not approve candidate A, implement a bootstrap helper, authenticate
the operator, or open Recovery Gate. A consistent generic observation does
not mean that a sudo invocation or its ancestor chain is accepted. V3/V4 and
any privileged integration require separate design and explicit approval.
