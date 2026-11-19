# systemd socket activation probe

This is an opt-in integration probe, not a production unit or deployment recipe.

It exercises a real systemd **user** manager, using unique unit names and a
private directory under XDG_RUNTIME_DIR. It does not use sudo, create users,
touch system units, write under /run/system, access Atlas databases, or contact
the existing Atlas services.

## What it checks

- A filesystem AF_UNIX/SOCK_SEQPACKET listener is created by systemd.
- The socket is owned by the invoking user and has mode 0600; its private
  parent directory has mode 0700.
- The socket path is absent before activation and is created inside a fresh
  mode-0700 runtime directory. The probe deliberately does not place an object
  at the path before systemd binds it.

### Observed collision result

On the current development host (Debian systemd 257.13), the user manager
returned success from `systemctl start`, left the socket unit active, and a
pre-existing regular file at the configured socket path remained a regular
file but no longer contained its sentinel bytes. This demonstrates that the
filesystem socket activation path must not be assumed to reject collisions
safely. The probe no longer performs this destructive collision experiment;
it only activates a socket at a path that is absent inside a fresh private
runtime directory. This is an observed result for that host, not a claim about
every systemd release.

Until the behavior is understood and a safe pathname ownership strategy is
demonstrated, systemd filesystem socket activation is **not an approved Atlas
design choice**. Do not deploy this unit or infer that the private directory
settings alone make collision handling safe.
- With Accept=no, the service receives the listening descriptor as fd 3 and
  validates LISTEN_PID, LISTEN_FDS, AF_UNIX and SOCK_SEQPACKET.
- The service accepts one ping and exits; a second connection activates it
  again using the same systemd-owned listener.
- The service does not unlink the socket path. With RemoveOnStop=no, stopping
  the socket unit leaves pathname cleanup to the owner/operator.

## Run

From the repository root, in a session where systemd --user is available:

```bash
python tests/integration/systemd_socket_activation/run_user_manager_test.py
```

The probe is intentionally not part of unittest discovery. It creates two
uniquely named files in ~/.config/systemd/user, reloads the user manager, and
creates one uniquely named directory under XDG_RUNTIME_DIR. Unit files are
created with exclusive creation (no overwrite or symlink following), and the
probe records device, inode and object type for each resource it creates.
Cleanup removes a unit file, socket path, or directory only if its current
identity still matches the recorded object; a replacement is left untouched
and reported for manual inspection. The probe stops only its own uniquely
named units and reloads the user manager. It does not change the manager's
default target or enable units.

The identity check is a defensive cleanup guard, not an atomic unlink-by-inode
primitive. The probe assumes its user-owned unit directory and private runtime
directory are not being concurrently manipulated by a hostile process running
under the same UID. It does not claim protection against that same-UID race.

If the command is interrupted or the machine shuts down mid-run, inspect the
printed unique unit names and temporary directory before removing anything.
Do not use broad wildcard cleanup commands.

A missing systemd user manager is a hard prerequisite failure; do not switch
to sudo or system units to force the test. In that case, report the exact
message and we will choose a separate disposable VM/container test strategy.

## Limits

This probe validates the user-manager activation mechanics. It does **not**
prove system-manager behavior with SocketUser=atlas-runtime, a root-owned
socket directory, system service sandboxing, privilege dropping, or the
future privileged administrative client. Those require a separate disposable
system-level test before production approval.

It also does not implement a persistent Atlas listener or any administrative
operation beyond the existing non-mutating authority.ping protocol.
