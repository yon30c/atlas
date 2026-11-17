# Bootstrap invocation probe (diagnostic only)

This small Linux C program collects process-parent and controlling-TTY facts for
the LOCAL bootstrap design review.

## Strict limits

- It is not the PAM helper.
- It does not authenticate or authorize anyone.
- It does not read secrets, protected bootstrap configuration, or signing keys.
- It does not write SQLite/CAM, create proofs, or change host configuration.
- It must not be installed under /usr/libexec, run setuid, or receive file capabilities.
- Its output is diagnostic evidence only. It is not a security decision.

## Build on Debian

From the repository root:

\`\`\`sh
cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \\
  -o /tmp/atlas-bootstrap-probe \\
  tools/bootstrap-probe/bootstrap_probe.c
\`\`\`

The resulting binary is placed in /tmp, not in a privileged system path.

## Run

First, from an ordinary interactive shell:

\`\`\`sh
/tmp/atlas-bootstrap-probe
\`\`\`

Then, from the same shell:

\`\`\`sh
sudo -- /tmp/atlas-bootstrap-probe
\`\`\`

Repeat from an SSH session with PTY:

```sh
ssh -t HOST 'sudo -- /tmp/atlas-bootstrap-probe'
```

For the no-PTY case, first run the probe directly (this isolates the TTY
observation from sudo's own password/TTY policy):

```sh
ssh -T HOST '/tmp/atlas-bootstrap-probe'
```

Optionally try the sudo invocation without a PTY:

```sh
ssh -T HOST 'sudo -n -- /tmp/atlas-bootstrap-probe'
```

The last command may be rejected by sudo before the probe starts if no valid
sudo timestamp is cached or the policy requires interactive authentication.
That is a sudo-layer result, not a probe result. The direct no-PTY run should
report that /dev/tty cannot be opened. Do not treat any other output as a
pass/fail security verdict.

Replace HOST with the actual SSH destination or configured alias. Review
output before sharing it; process names and terminal metadata may reveal
operational details.

## What it reports

- Current process IDs and real/effective UID/GID.
- Immediate parent PID, /proc/PID/status UID/GID/PPID values.
- pidfd_open availability and immediate poll state.
- Parent executable inode, ownership, mode, and informational symlink target.
- Parent `/proc/PID/stat` session, process group, `tty_nr`, and `tpgid` fields.
- Parent file descriptors 0, 1, and 2 as informational symlink targets.
- Controlling terminal SID, process SID, foreground process group, process group,
  and device metadata.

The probe deliberately does not compare these values against an allowlist. The
next design step is to review the observations from the actual C implementation
before specifying a validator.
