# A-IPC-01 — private Unix listener probe

**Status:** opt-in experimental probe implemented and owner-validated on
commit `1d5bdb122a8480c36b445be7dd961b93806de74b`: A01–A16 all PASS,
including A09a (DAC) and A09b (SO_PEERCRED), with 0 SKIP and 0 FAIL.
The recorded Debian execution is documented below and in
[the validation record](../../../docs/status-aipc01-validation-2026-11-21.md).
This is not a production listener and does not select AF_UNIX pathname sockets
as the production IPC transport.

 
> **Current direction (2026-11-21):** the owner selected alternative A as the
> primary line of technical evaluation and development. This is not production
> transport approval. The owner-reported execution below supersedes all earlier
> A09 SKIP / INCOMPLETE statements in the historical notes: A01–A16 = 16 PASS,
> 0 SKIP, 0 FAIL on commit
> `1d5bdb122a8480c36b445be7dd961b93806de74b`. Historical sections are retained
> to preserve the sequence of implementation and preflight decisions; read them
> as historical snapshots, not as the current validation state. PR #30 remains
> Draft on the separate design branch `design/isolated-private-unix-listener-probe`;
> it is not this experimental branch and does not contain the A09-enabled run.
> See the
> [canonical validation record](../../../docs/status-aipc01-validation-2026-11-21.md).

## Scope and safety boundary

The probe creates one unique temporary sandbox under the current user's
temporary directory. It refuses UID 0, requires Linux and SO_PEERCRED, checks
that the temporary path components are real directories, and requires the
sandbox root and each scenario directory to be owned by the effective UID with
mode exactly 0700.

Each listener is AF_UNIX/SOCK_SEQPACKET; its pathname is created only inside
the sandbox and its mode is set and checked as exactly 0600. The runner never
uses sudo, changes UID/GID, changes host configuration, installs or invokes
systemd, accesses SQLite, or connects to Atlas services.

Collision handling never unlinks a pathname before bind(). Stale sockets are
not removed to make a bind succeed. Cleanup compares the current lstat()
identity (device, inode and file type) with the identity captured after a
successful bind. A mismatch is preserved and reported. The comparison followed
by unlink() is not atomic: this does not protect against root or a malicious
process running under the same UID.

The ping scenario imports the existing handler and exercises only
authority.ping under atlas-admin/1. The remaining six catalogued operations
are not called or enabled.

## Run manually on Debian

From the repository root, as the ordinary unprivileged account that owns the
checkout:

    PYTHONPATH=src python tests/integration/private_unix_listener/run_probe.py

Do not prefix the command with sudo. The runner does not run as part of the
default unit-test suite and must be invoked explicitly.

The runner prints one JSON report and returns:

- 0: PASS — every scenario passed and no conditional scenario was skipped.
- 1: FAIL — an invariant failed or sandbox cleanup could not be verified.
- 2: INCOMPLETE — a required precondition or conditional scenario was not
  demonstrated. INCOMPLETE is not a pass.

## Scenario coverage

| ID | Coverage |
|---|---|
| A01 | Private directory/socket modes; bind, listen, accept and close |
| A02 | Regular-file collision preserves identity and sentinel |
| A03 | Symlink collision preserves link and target |
| A04 | Second bind cannot replace an active listener |
| A05 | Stale socket collision is not auto-cleaned |
| A06 | Cleanup preserves a replacement pathname |
| A07 | Cleanup removes the unchanged socket created by this instance |
| A08 | Allowed peer completes one authority.ping request |
| A09a | DAC blocks a different-UID client from the private 0700/0600 candidate endpoint; no SO_PEERCRED authorization claim |
| A09b | Separate temporary fixture lets a different-UID client reach the handler; real SO_PEERCRED UID is rejected before request processing, with no protocol response |
| A10 | Allowed peer UID/PID/GID are read from kernel credentials and match the current authorized UID |
| A11 | Disconnect before request is handled without a fabricated response |
| A12 | Truncated packet and ancillary data are rejected without an error response |
| A13 | Idle peer is released by the bounded read timeout |
| A14 | Test-only bounded accept harness rejects excess clients and recovers capacity |
| A15 | A closed listener no longer accepts new connections |
| A16 | Two concurrent binds produce exactly one winner; winner remains operational |

A09 is split into two independent checks. Both remain SKIP by default unless
the operator explicitly enables them with the reviewed SSH identity, the host
forced command has been separately approved and updated, and shell startup
files have been reviewed. The owner has now reported one successful opt-in
execution; see the execution record below:

- **A09a (filesystem DAC):** use the candidate endpoint with its unchanged directory mode 0700 and socket mode 0600. A pre-existing different-UID process should be denied before the listener accepts the connection. This proves filesystem reachability isolation only; it does not exercise the handler's SO_PEERCRED allowlist.
- **A09b (application authorization):** use a separate, disposable fixture whose directory is traversable but not writable by other UIDs (for example 0711) and whose test socket permits connect (for example 0666). A different UID must reach the listener; the real handler must read SO_PEERCRED, reject that UID as UNAUTHORIZED_PEER, and send no protocol response. These relaxed permissions belong only to the isolated fixture and must never be applied to the candidate endpoint or treated as production settings. The fixture must be a sibling of the private probe sandbox, directly under a verified shared sticky temporary parent (such as /tmp), not nested inside the sandbox root (0700), because the parent directory's DAC permissions also govern traversal.

Both checks require a pre-existing unprivileged identity and an externally launched client. The runner must not create accounts, change UID/GID, use sudo, or alter host configuration. If the owner cannot safely provide that external peer, retain SKIP and overall INCOMPLETE. Do not replace the real credential exchange with mocks.

A14 tests the resource ceiling of this temporary probe harness, not a production
listener implementation. Admitted workers are held behind a test-only release
gate until saturation has been observed, so the rejection check does not depend
on the handler read timeout or thread scheduling. Unexpected worker exceptions
are reported as failures. Its fixed experimental limits are included in the
JSON report; they do not establish production capacity values.

## Interpreting the report

The JSON includes the checkout commit, kernel, Python version, effective UID,
temporary sandbox path, fixed limits, per-scenario status/duration, overall
classification, cleanup result, and observed peer PID/UID/GID for the successful ping cases.

Any FAIL involving a changed pre-existing object, an unexpected unlink, a
peer receiving a response when the contract requires silence, an unbounded
resource count, or cleanup uncertainty is a stop condition. Preserve the JSON
report and the checkout commit for review; do not rerun against any host path.

A successful run does not demonstrate protection from root or same-UID
processes, multi-UID authorization, production service lifecycle, systemd
activation, separation of privileges, SQLite authorization, or suitability
for deployment. It does not approve a persistent listener or any administrative
operation beyond the non-mutating ping used as a protocol fixture.


## Owner-reported execution — 2026-11-20

The owner ran the command above without sudo on Debian 13 from checkout
`314e7395fbc972f8b9ab4a10dd800e85c11c7b59`.

- Kernel: `6.12.117+deb13-amd64`; Python: `3.13.5`; effective UID: `1000`.
- Overall: `INCOMPLETE`; duration: `0.876 s`; cleanup:
  `empty sandbox root removed`.
- A01–A08 and A10–A16: PASS (15 scenarios).
- A09: SKIP; no different-UID peer was tested. The runner intentionally does
  not change UID/GID, use sudo, or assume another identity.
- No scenario reported FAIL.

A14 observations: peak active workers 2, six rejected connections, eight
handled connections, and zero active connections after recovery. A16 observed
exactly one successful concurrent bind, and the winning listener remained
operational. A08/A10 observed peer PID 3751, UID 1000 and GID 1000.

This confirms only the experimental cases actually exercised. In particular,
it does not establish multi-UID rejection, production authorization, privilege
separation, resistance to root or same-UID malicious processes, persistent
service lifecycle, systemd integration, SQLite authorization, or production
suitability. Keep the overall result classified as INCOMPLETE while A09 is
unverified; do not relabel it PASS.


## A09 security-layer distinction

The candidate endpoint's DAC boundary (directory 0700, socket 0600) prevents another UID from reaching the listener. A kernel-level access denial occurs before accept() and therefore cannot prove that the application inspected SO_PEERCRED. A09a records this filesystem control.

A09b tests the separate application control with a disposable fixture that intentionally permits connection from the external test UID. Its permissions are test scaffolding only; it does not weaken or replace the candidate endpoint's DAC boundary. The two results must be reported separately.


### A09 external-identity execution prerequisite

The private sandbox root is 0700. An A09b fixture nested below it would remain unreachable to a different UID regardless of the fixture's own 0711 mode. The fixture must instead be created as a separate temporary directory directly under a verified shared sticky temporary parent (for example /tmp), with its own mode 0711 and test socket mode 0666. The candidate endpoint remains unchanged.

The initial two-terminal coordination proposal was superseded by the bounded SSH-subprocess implementation described in the A-IPC-01 design document. The runner remains under the ordinary checkout UID and starts a local SSH client; sshd launches only the fixed forced-command helper under the distinct peer UID. The runner must not invoke sudo, su, runuser, setuid, systemd, or any credential-switching mechanism.


## A09 temporary external identity design

A dedicated temporary account `atlas-a09-test` has been created and verified by the owner in Debian. Its UID is `1001`, primary GID `984`, its only reported group is the dedicated `atlas-a09-test` group, its HOME `/var/lib/atlas-a09-test` is mode `0700`, its shell is `/bin/bash`, and its password is locked (`passwd -S` state `L`). See [the provisioning record and remaining procedure](../../../docs/design/a09-temporary-test-identity-provisioning.md).

The existing `atlas-sandbox` account is excluded because it belongs to the earlier Atlas Broker/rootless-container environment and has an active lingering user manager. Do not reuse, unlock, stop or modify it.

The peer identity is provisioned. The owner reported a read-only inactivity check: `ps -u atlas-a09-test` returned no processes; `loginctl show-user` reported that UID 1001 is neither logged in nor lingering; `user@1001.service` is inactive; the linger file is absent; and `sudo -l -U atlas-a09-test` confirmed no sudo permission. This is a point-in-time check and does not prove that no unrelated system unit references the account. SSH preflight found public-key authentication enabled, keyboard-interactive disabled and strict modes enabled; X11, TCP and agent forwarding are globally enabled. The SSH daemon listens on all interfaces and the reported nftables INPUT policies are ACCEPT; this experiment does not establish global SSH isolation and must not modify SSH/PAM/firewall. The loopback ED25519 host-key fingerprint matched the locally inspected host key: `SHA256:txiDPT+/ldcIwnN6BPotbeL7QsofAieAeqF3GKMa9xI`.

The owner subsequently installed an ephemeral Ed25519 key restricted with `from="127.0.0.1",restrict` and forced command `/usr/bin/id -u`. A strict local SSH connection returned `1001`, confirming key authentication and the forced identity command. The private key remains outside the repository. This does not validate A09a/A09b. The helper/runner are now implemented on this branch; changing the forced command to the reviewed A09 helper is a separate host change requiring explicit approval. The latest execution evidence remains 15 PASS + original A09 SKIP + 0 FAIL / INCOMPLETE.


## A09 SSH identity — current status (2026-11-21)

The owner installed an ephemeral Ed25519 key for `atlas-a09-test` and confirmed one strict loopback SSH authentication. The authorized key currently uses:

```text
from="127.0.0.1",restrict,command="/usr/bin/id -u"
```

The forced command returned UID `1001`. The private key remains under the owner's private runtime directory and is not in the repository. The temporary known_hosts file is owner-only and the ED25519 host key was pinned after fingerprint comparison.

This proves SSH public-key authentication and the forced identity command only. It does not exercise either A09 subscenario. The A09a/A09b helper and runner have since been implemented on this branch, but remain unexecuted and unvalidated. The last owner-reported execution still predates that implementation and remains 15 PASS + original A09 SKIP + 0 FAIL / INCOMPLETE.

The orchestration design and implementation details are recorded in [the A-IPC-01 design](../../../docs/design/local-authority-admin-private-unix-listener-probe.md#16-diseño-de-coordinación-externa-para-a09aa09b--2026-11-21). The current authorized-key forced command remains `/usr/bin/id -u`; replacing it with the fixed helper is a separate host security change requiring explicit approval. Do not change it or run A09 yet.


## A09 helper/runner implementation — 2026-11-21

The following code is now present on the experimental branch:

- `a09_ssh_client.py`: fixed standard-library-only remote helper. It accepts one JSON instruction up to 4096 bytes, allows only A09a/A09b and the corresponding probe socket path shapes, rejects a non-empty `SSH_ORIGINAL_COMMAND`, never executes shell commands, never changes credentials, and does not access the checkout. Its stdout/stderr exchange is capped at 4096 bytes per stream; the helper emits at most 2048 bytes.
- `run_probe.py`: A09a and A09b are separate report rows. A09 remains disabled by default. Enabling it requires all of:
  - `--enable-a09`;
  - `--a09-identity-file` and `--a09-known-hosts`;
  - `--a09-forced-command-confirmed`, acknowledging the separately approved host-side `authorized_keys` forced-command update;
  - `--a09-shell-startup-reviewed`, acknowledging read-only review of the peer account's shell startup files.
- Preflight checks the peer account UID/GID from the local account database, requires a distinct non-root identity, exact key/known_hosts ownership and modes, no hard links, known_hosts directly under `/tmp`, the previously verified loopback ED25519 host-key fingerprint, and `/tmp` as a root-owned 01777 directory.
- SSH is invoked with `-F /dev/null`, an explicit identity, `IdentityAgent=none`, public-key-only authentication, strict host-key checking, ED25519-only algorithms, no PTY, no forwarding, no proxy, no control master and a bounded connection/total timeout. No remote command is supplied; the authorized-key forced command is the only remote entrypoint.
- The helper is copied to `/tmp/atlas-a09-client.py` with exclusive creation, mode 0644, and identity-checked cleanup. A pre-existing helper path is never overwritten.
- A09a requires external `EACCES`, zero accepted connections and unchanged candidate endpoint identity/modes.
- A09b requires the kernel-observed peer PID/UID/GID to match the helper/account, the real handler to raise `UNAUTHORIZED_PEER`, a non-empty ping request to have been sent, and zero response bytes before EOF/reset. The temporary fixture is a sibling directly under `/tmp`, directory 0711/socket 0666; the candidate endpoint remains 0700/0600.
- If the SSH child cannot be stopped, the runner preserves the helper/socket/fixture rather than deleting resources that may still be in use; this is a failure requiring manual inspection.

### Do not run A09 yet

The installed key still forces `/usr/bin/id -u`. The implementation expects the separately approved forced command:

```text
/usr/bin/python3 -I /tmp/atlas-a09-client.py
```

Changing `authorized_keys` is a host security change and has **not** been authorized or performed. Before that change, the owner must also inspect the peer account's `.bashrc`, `.bash_profile`, `.profile` and relevant shell startup behavior read-only. No SSH/PAM/firewall changes are permitted.

After those independent gates are completed, the opt-in form is:

```bash
PYTHONPATH=src python tests/integration/private_unix_listener/run_probe.py \
  --enable-a09 \
  --a09-identity-file /path/to/id_ed25519 \
  --a09-known-hosts /path/to/known_hosts \
  --a09-forced-command-confirmed \
  --a09-shell-startup-reviewed
```

The example is documentation only and must not be run until the host change and execution are explicitly approved. A normal invocation without these options leaves A09a/A09b as SKIP and the global result INCOMPLETE.

**Validation status:** static code review of the helper/runner is complete in GitHub; no tests, builds or workflows were run. The implementation has not been executed or validated. The owner must inspect shell startup behavior read-only, authorize any host-side forced-command change separately, and execute the probe locally on Debian. `main` remains untouched; no PR exists and no production transport is approved.


## Owner-reported execution — 2026-11-21 (A09 enabled)

The owner executed the opt-in runner on Debian 13 from checkout
`1d5bdb122a8480c36b445be7dd961b93806de74b`, as unprivileged UID 1000,
with the pre-provisioned peer account `atlas-a09-test` (UID 1001, GID 984).
Kernel: `6.12.117+deb13-amd64`; Python: `3.13.5`; duration: `1.72 s`.

**Reported result: `overall=PASS`; all 16 scenarios A01–A16 passed.**
There were no SKIP or FAIL rows. Cleanup reported
`empty sandbox root removed`.

A09 evidence:

- **A09a — DAC:** external peer UID 1001/GID 984/PID 5405 received
  `EACCES` (`errno=13`) connecting to the candidate endpoint. The listener
  accepted zero connections. Candidate socket remained owned by UID 1000,
  mode 0600; candidate directory mode remained 0700.
- **A09b — SO_PEERCRED:** external peer UID 1001/GID 984/PID 5417 connected
  to the separate fixture (directory mode 0711, socket mode 0666). The real
  handler rejected it with `UNAUTHORIZED_PEER`. The client observed reset
  and received zero response bytes after sending a 122-byte ping request.
- The temporary sandbox root was removed successfully.

The existing A01–A08 and A10–A16 scenarios also reported PASS. A14 observed
peak_active=2, rejected_connections=6, handled_connections=8 and
active_after_recovery=0. A16 observed exactly one bind winner and a
functioning winner listener.

This owner-reported result validates only the experimental probe scenarios
actually exercised on the recorded commit and host. It does **not** approve
a persistent listener, select AF_UNIX pathname sockets for production, enable
any administrative operation beyond the non-mutating ping fixture, prove
protection against root or same-UID malicious processes, validate systemd
activation, privilege separation, SQLite authorization, or authorize
deployment. SSH/PAM/firewall global configuration was not changed as part of
the reported run.


## A-IPC-02 — mutual authentication and bounded-capacity probe

**Status:** six initial scenarios were owner-validated on commit
`fbc8c68e75c7d5d32768442666cf861f7880eb28` with PASS and cleanup verified;
the overall probe correctly returned INCOMPLETE because required coverage
remained. The current branch adds MA-03 in commit `7a0d4f1`, pending owner
execution. This is not a production listener or transport approval. It is separate from the unprivileged A-IPC-01 runner above:
A-IPC-01 continues to refuse EUID 0; A-IPC-02 requires direct root execution
inside a disposable VM because it must prove a real EUID 0 client against
service and alternate numeric fixture identities.

The runner creates a fresh root-owned mode-0700 private sandbox and a separate
root-owned mode-0711 traversal fixture root under `/run`. The latter permits the
alternate-UID client to reach a deliberately exposed fixture socket; it is not
writable by group/others. It stages read-only copies of the probe and IPC module
under that traversal root so dropped-UID child processes can execute/import them.
Only temporary fixture directories and socket pathnames are created.
It does not create NSS users/groups, edit host configuration, invoke sudo/su,
install systemd units, access SQLite, or connect to any Atlas service. The
service child clears supplementary groups, sets real/effective/saved GID and
UID to the supplied numeric fixture values, and caps its own
`RLIMIT_NOFILE` at 64. No host account provisioning is performed.

The fixture IDs must be dedicated, unused numeric identities in the disposable
VM. The operator is responsible for selecting them and explicitly confirming
that the VM and IDs are disposable fixtures. Do not use IDs belonging to
real host users/groups or run this probe on the production server.

### Invocation

From the repository root, in a disposable Debian/Linux VM, start a root shell
directly (do not use sudo for this probe), then supply four dedicated numeric
fixture IDs:

```sh
read -r -p "UID numérico reservado para atlas-runtime fixture: " SERVICE_UID
read -r -p "GID numérico reservado para atlas-runtime fixture: " SERVICE_GID
read -r -p "UID numérico reservado para peer alternativo: " OTHER_UID
read -r -p "GID numérico reservado para peer alternativo: " OTHER_GID

PYTHONPATH=src python3 tests/integration/private_unix_listener/run_mutual_auth_capacity_probe.py \
  --service-uid "$SERVICE_UID" \
  --service-gid "$SERVICE_GID" \
  --other-uid "$OTHER_UID" \
  --other-gid "$OTHER_GID" \
  --confirm-disposable-vm \
  --confirm-fixture-ids
```

The command is intentionally not part of the default test suite. Do not invent
or reuse IDs from the host; first reserve four numeric fixture IDs exclusively
inside the disposable VM. The runner does not create accounts or groups.

### Owner-reported baseline execution — 2026-11-21

The owner executed A-IPC-02 in the disposable VM `Atlas-VM-test`, directly
as root, on commit `fbc8c68e75c7d5d32768442666cf861f7880eb28`, using fixture
UID/GID pairs 2005/2005 and 2006/2006. Debian 13, kernel
`6.12.117+deb13-amd64`, Python 3.13.5.

- MA-01, MA-02, MA-04 and MA-05: PASS.
- CP-01 and CP-04: PASS; observed maximum active workers 4, and zero active
  workers after recovery.
- Kernel backlog was configured to 8 but exact saturation was not tested.
- Overall: INCOMPLETE, as required while omitted scenarios remain.
- Duration: 1.177 s.
- Cleanup: both private and traversal `/run` sandboxes removed after child
  processes exited.
- No FAIL rows were reported.

This execution validates only the six scenarios above on the recorded
commit/environment. The current MA-03 addition was authored afterward in
commit `7a0d4f1` and has not yet been executed. Do not attribute MA-03 PASS
or the baseline run to the newer commit.

### Implemented evidence in this increment

| Scenario | Evidence |
|---|---|
| MA-01 | Root client verifies the server's kernel UID before sending a valid ping |
| MA-02 | Root client rejects a server running under the alternate UID and sends zero bytes |
| MA-03 | Non-root client fixture is rejected by the EUID guard before socket creation/connect; server observes no connection (new code, pending owner execution) |
| MA-04 | Service receives a real kernel peer UID 0 and processes the ping |
| MA-05 | Service rejects the alternate-UID client before calling recv and sends no response |
| CP-01 | Four active workers occupy all slots; a fifth connection remains pending rather than creating a fifth worker |
| CP-04 | After a slot is released, the queued connection is accepted and the service returns to zero active workers |

The probe verifies the service child's real/effective/saved UID/GID, empty
supplementary groups, socket ownership/mode and `RLIMIT_NOFILE=64`; it records
the configured backlog, read/write timeout and global deadline. Behavioral
tests for timeout expiry and exact backlog saturation remain incomplete.

**Not yet implemented/validated:** exact kernel backlog saturation; full
open-FD accounting; idle/read/write deadline adversaries; exception-path
worker recovery; request/response boundary and JSON-depth adversaries;
configuration parsing/immutability;
pathname component-walk, symlink and collision matrix; stale recovery.
The current runner reports these omitted scenarios as INCOMPLETE, never PASS.
A complete overall result is therefore expected to be INCOMPLETE at this stage.

### Safety and result codes

- Run only in a disposable VM with root access and four numeric IDs reserved
  exclusively for the fixture.
- The process drops credentials only in child processes; no host account,
  group, permission, service or global configuration is changed.
- Temporary data is confined to fresh root-owned `/run/atlas-mutual-auth-*`
  and `/run/atlas-mutual-auth-public-*` directories. The public traversal root
  is mode 0711 and not writable by group/others. If a child fails to stop or a
  socket pathname identity cannot be verified, the sandboxes are preserved and
  the report is FAIL.
- 0: PASS (all required scenarios implemented and passed; not expected yet).
- 1: FAIL (an implemented invariant failed or cleanup could not be verified).
- 2: INCOMPLETE (preconditions unavailable or scenarios remain unimplemented).

No tests, builds or workflows have been run by the assistant. The owner must
review and execute this probe manually. A-IPC-02 does not implement or approve
a persistent listener or production transport.


## A-IPC-02 owner validation and MA-06 update — 2026-11-21

The owner executed the A-IPC-02 runner in disposable VM `Atlas-VM-test`,
directly as root, on commit
`069dbb9520f9e640955d9122f3a8012b2f55ba1a`, Debian 13, kernel
`6.12.117+deb13-amd64`, Python 3.13.5, with SERVICE UID/GID 2005/2005
and OTHER UID/GID 2006/2006.

- MA-01 through MA-05: PASS.
- MA-03 specifically observed client EUID 2006, `connect_attempted=false`,
  and `server_observed_connection=false`.
- CP-01 and CP-04: PASS; maximum active workers 4; active workers after
  recovery 0.
- Backlog 8 was configured but not saturated.
- Overall INCOMPLETE; duration 1.339 s; private and traversal `/run`
  sandboxes removed after child processes exited.
- No FAIL rows were reported.

This evidence belongs to commit `069dbb9` only. The subsequent MA-06
implementation is in commit `9a8380e` and has not been executed.

### MA-06 — reject client-supplied identity claims

The runner now sends a valid ping envelope augmented with untrusted top-level
`uid`, `gid` and `pid` claims. The fixture authenticates the connected
peer using kernel SO_PEERCRED first, then passes the packet through the strict
request decoder. MA-06 requires rejection with `INVALID_REQUEST`, while the
observed peer UID remains the kernel UID (root in this scenario); the supplied
identity fields are not accepted as credentials.

MA-06 is implemented but pending owner execution. This is a protocol-envelope
negative test, not proof against a compromised root client or kernel. The
overall runner remains INCOMPLETE until the remaining MA/CP scenarios are
implemented and owner-validated.



## A-IPC-02 — validación del propietario de MA-06 (2026-11-21)

El propietario ejecutó el runner directamente como root en la VM desechable
`Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`, Python
`3.13.5`, sobre el commit `b4eda57d36338f065adb2cb4e00d19a8ade58069`,
con fixtures SERVICE UID/GID `2005/2005` y OTHER UID/GID `2006/2006`.

- **MA-01..MA-06: PASS.** Cliente root autenticó el servidor UID 2005 y
  completó ping. El cliente rechazó el servidor UID 2006 antes de enviar
  bytes (`bytes_sent_by_client=0`). El servidor rechazó al peer UID 2006
  antes de leer (`response_bytes=0`). El cliente no-root EUID 2006 fue
  rechazado antes de connect (`connect_attempted=false`; el servidor no
  observó conexión).
- **MA-06:** el envelope ping incluía claims top-level falsos
  `uid=0`, `gid=0`, `pid=1`. El decoder respondió
  `INVALID_REQUEST`; la evidencia de identidad conservó
  `kernel_peer_uid=0`. Los campos aportados por el cliente no se aceptaron
  como credenciales.
- **CP-01/CP-04: PASS.** Máximo observado de workers/conexiones activas: 4;
  después de liberar carga, `active_after_recovery=0`.
- Backlog del kernel configurado en 8, **sin saturación exacta**.
- Duración: 1.431 s. Cleanup confirmado: sandboxes privado y de traversal
  bajo `/run` eliminados después de finalizar los procesos hijos.
- Resultado global: **INCOMPLETE**, sin escenarios FAIL.

La evidencia aplica al commit y entorno indicados; no se extiende a commits
posteriores sin repetir la ejecución. Permanecen sin implementar o validar
MA-07..MA-10 y CP-02..CP-03/CP-05..CP-12: configuración ausente/duplicada/
desconocida/alterada y snapshot inmutable; desconexión y variantes de
transporte; saturación exacta del backlog; adversarios de read/write/deadline;
recuperación ante excepciones; límites de payload/profundidad JSON y
contabilidad completa de FDs.

**Siguiente incremento propuesto:** revisar y diseñar MA-07/MA-08 antes de
codificar. El diseño de configuración confiable exige parser cerrado,
resolución segura desde descriptor, validación de tipo/owner/mode/tamaño,
fallo cerrado e inmutabilidad en memoria. La propuesta de
`/etc/atlas/admin-ipc.conf` sigue siendo solo diseño: no existe archivo
operativo, parser productivo ni entrypoint IPC revisado. Cualquier fixture
MA-07/08 debe vivir exclusivamente en sandbox temporal y no leer ni crear
configuración del host.

No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. El
propietario ejecutó el probe localmente en la VM indicada. `main` no se
modificó, no se creó PR y no se aprobó listener persistente, transporte de
producción ni despliegue.
