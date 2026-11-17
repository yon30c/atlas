# Bootstrap chain observer — candidate A diagnostics

This is an unprivileged, read-only diagnostic prototype. It is not the
bootstrap authenticator, not a policy authority, and not an approval to run a
privileged helper.

## Scope

The observer checks whether the currently running process has a direct
parent whose observed executable metadata is compatible with a root-owned,
setuid sudo binary; whether the parent's UID/GID tuple matches the observed
sudo execution pattern; whether the process/TTY/session relations are
consistent; and whether the first non-sudo ancestor has the originating TTY
that is also observed on the outermost sudo monitor.

It walks only the bounded direct ancestry needed to find the first
non-sudo ancestor after a contiguous sudo-like chain. A shell or wrapper as
the direct parent is rejected even if a sudo process exists above it.

A "sudo candidate" classification is only a diagnostic comparison of:
- executable basename sudo;
- regular file metadata;
- root ownership;
- setuid bit;
- no group/other write permission.

It does not prove package identity, executable provenance, policy integrity,
or that the executable is the approved sudo build. Those require protected
configuration and independent host/package review, which are out of scope.

## Safety boundary

- Read-only procfs, pidfd_open/poll, O_PATH/fstat, readlink, and TTY
  queries only.
- No shell-outs, network, file writes, PAM, sudo invocation, environment-based
  identity, keys, configuration, installation, package changes, sudoers,
  systemd, SSH, Broker, SQLite, CAM, or runtime integration.
- The program never asks for privileges. Run it as the current user for a
  negative diagnostic, or manually through sudo only if the operator chooses.
- It never accepts command-line arguments.
- It emits only CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY, CHAIN_MISMATCH, or
  CHAIN_INCOMPLETE; none means ALLOW or AUTHORIZED.
- All binaries are written to /tmp; do not install them.

The collector opens pidfds for observed ancestors, captures bounded
status/stat and executable metadata twice, checks PID/starttime/credentials
and parent links, checks pidfd liveness, and rechecks the caller's own stat record, PPID, session, process group and
TTY. It also requires the helper's tty_nr to match the direct sudo parent's
tty_nr. These are bounded observations, not an atomic
kernel snapshot. pidfd does not freeze credentials, PPID, executable or TTY.

## Build and automated tests

From the repository root on Debian:

    sh tools/bootstrap-chain-observer/test_chain.sh

The suite uses strict C11 warnings as errors, fixture tests for the direct
sudo pattern, wrapper rejection, credential/session/TTY mismatches, missing
evidence, unstable observations, executable metadata, self/parent TTY binding,
output escaping and non-authoritative output, plus a live unprivileged smoke
test and argument rejection.

## Manual scenarios

Only after the automated suite passes:

    # Ordinary user invocation: expected CHAIN_MISMATCH (no direct sudo parent)
    /tmp/atlas-bootstrap-chain-observer

    # Direct sudo from local terminal: diagnostic pattern should match
    sudo -- /tmp/atlas-bootstrap-chain-observer

    # SSH with PTY and direct sudo (from the Windows client)
    ssh -t greed@10.0.0.81 'sudo -- /tmp/atlas-bootstrap-chain-observer'

    # SSH with PTY and shell intermediary: direct parent must be rejected
    ssh -t greed@10.0.0.81 'sudo -- sh -c "/tmp/atlas-bootstrap-chain-observer"'

    # SSH without PTY, ordinary invocation
    ssh -T greed@10.0.0.81 '/tmp/atlas-bootstrap-chain-observer'

Do not use sudo -S, NOPASSWD, timestamp changes, or configuration changes.
If sudo refuses to execute a no-PTY command because it cannot authenticate,
that case is inconclusive; do not work around it.

If a no-PTY sudo command is already permitted by the existing timestamp and
sudo policy, it may be tested only as an optional diagnostic. The expected
result is a mismatch when the first non-sudo ancestor has no controlling TTY,
even if sudo has created an internal PTY for its command. Do not create such a
condition or change policy to force the test.

## Result interpretation

- CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY: the sampled process chain matched
  the narrow candidate-A shape, including a direct sudo-like parent and a
  non-sudo origin ancestor whose TTY is bound to the outermost sudo monitor.
  This is not authentication, authorization, or proof of physical presence.
- CHAIN_MISMATCH: an observed relation contradicted the pattern, such as a
  wrapper/direct parent other than sudo, unexpected sudo credentials, a
  session/foreground mismatch, or absent/mismatched originating TTY.
- CHAIN_INCOMPLETE: required evidence could not be collected or remained
  unstable.

The source TTY check is intended to distinguish an SSH session that supplied
a PTY from a PTY created internally by sudo: the observer looks beyond the
sudo process(es) to the first non-sudo ancestor and checks its TTY relationship
to the outermost sudo monitor. This remains a diagnostic inference tied to
the observed process topology and sudo build/configuration; it is not a
cryptographic assertion about SSH or physical presence.

A matching result does not approve candidate A. The sudo package/version,
effective sudo policy, monitor behavior, executable trust reference, PAM,
protected configuration, key custody, and the residual process/TTY races
remain unvalidated. No helper installation or privileged integration is
authorized by this prototype.
