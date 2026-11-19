"""Opt-in integration probe for a private systemd --user SOCK_SEQPACKET socket.

Run manually; this is intentionally not part of the default unit-test suite.
It creates uniquely named transient user unit files and a private runtime dir,
then removes only those resources.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[3]
HELPER = Path(__file__).with_name("activated_service.py")
PYTHON = Path(sys.executable)


def _path_identity(path: Path) -> tuple[int, int, int]:
    info = path.lstat()
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


def _identity_matches(path: Path, identity: tuple[int, int, int], kind: str) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    expected_type = {"file": stat.S_IFREG, "socket": stat.S_IFSOCK, "directory": stat.S_IFDIR}[kind]
    return (
        (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)) == identity
        and stat.S_IFMT(info.st_mode) == expected_type
    )


def _unlink_if_same_identity(
    path: Path, identity: tuple[int, int, int] | None, kind: str
) -> bool:
    """Unlink only the recorded object; never remove a replacement at this path."""
    if identity is None:
        return False
    try:
        info = path.lstat()
    except FileNotFoundError:
        return True
    expected_type = {"file": stat.S_IFREG, "socket": stat.S_IFSOCK}[kind]
    current_identity = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
    if current_identity != identity or stat.S_IFMT(info.st_mode) != expected_type:
        return False
    path.unlink()
    return True


def _rmdir_if_same_identity(
    path: Path, identity: tuple[int, int, int] | None
) -> bool:
    """Remove an empty directory only while its recorded identity is present."""
    if identity is None:
        return False
    try:
        info = path.lstat()
    except FileNotFoundError:
        return True
    current_identity = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
    if current_identity != identity or not stat.S_ISDIR(info.st_mode):
        return False
    path.rmdir()
    return True


def _create_exclusive_file(path: Path, content: str) -> tuple[int, int, int]:
    """Create a private unit file without following or overwriting any path."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    identity = None
    try:
        os.fchmod(descriptor, 0o600)
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(content)
        return identity
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if identity is not None:
            _unlink_if_same_identity(path, identity, "file")
        raise


def _ensure_directory_chain(directory: Path) -> dict[Path, tuple[int, int, int]]:
    """Create missing unit directories and record only directories created here."""
    missing = []
    cursor = directory
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise RuntimeError(f"cannot find an existing parent for {directory}")
        cursor = parent

    existing = cursor.lstat()
    if not stat.S_ISDIR(existing.st_mode):
        raise RuntimeError(f"unit directory ancestor is not a real directory: {cursor}")

    created: dict[Path, tuple[int, int, int]] = {}
    for candidate in reversed(missing):
        try:
            candidate.mkdir(mode=0o700)
        except FileExistsError:
            info = candidate.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise RuntimeError(f"unit directory path was replaced: {candidate}")
            continue
        created[candidate] = _path_identity(candidate)
    target_info = directory.lstat()
    if not stat.S_ISDIR(target_info.st_mode):
        raise RuntimeError(f"unit directory is not a real directory: {directory}")
    return created


def run_systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["systemctl", "--user", *args]
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )
    if check and result.returncode:
        rendered = " ".join(command)
        diagnostics = ""
        if len(args) >= 2 and args[0] == "start" and args[1].endswith(".socket"):
            unit = args[1]
            status = subprocess.run(
                ["systemctl", "--user", "status", unit, "--no-pager", "--full"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
            journal = subprocess.run(
                ["journalctl", "--user", "-b", "-u", unit, "--no-pager", "-n", "60"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
            service_unit = unit.removesuffix(".socket") + ".service"
            service_status = subprocess.run(
                ["systemctl", "--user", "status", service_unit, "--no-pager", "--full"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
            service_properties = subprocess.run(
                ["systemctl", "--user", "show", service_unit,
                 "--property=LoadState,FragmentPath,UnitFileState", "--no-pager"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
            service_cat = subprocess.run(
                ["systemctl", "--user", "cat", service_unit],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
            diagnostics = (
                f"\nunit status:\n{status.stdout or status.stderr or '(empty)'}"
                f"\nuser journal:\n{journal.stdout or journal.stderr or '(empty)'}"
                f"\nassociated service properties:\n{service_properties.stdout or service_properties.stderr or '(empty)'}"
                f"\nassociated service status:\n{service_status.stdout or service_status.stderr or '(empty)'}"
                f"\nassociated service definition:\n{service_cat.stdout or service_cat.stderr or '(empty)'}"
            )
        raise RuntimeError(
            f"{rendered} failed with exit code {result.returncode}.\n"
            f"stdout:\n{result.stdout or '(empty)'}\n"
            f"stderr:\n{result.stderr or '(empty)'}{diagnostics}"
        )
    return result


def quote_unit(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def wait_for(predicate, description: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for {description}")


def active_state(unit: str) -> str:
    result = run_systemctl("show", "--property=ActiveState", "--value", unit, check=False)
    return result.stdout.strip()


def send_ping(path: str) -> dict:
    request_id = str(uuid.uuid4())
    packet = json.dumps(
        {
            "version": 1,
            "request_id": request_id,
            "operation": "authority.ping",
            "payload": {},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    client.settimeout(5.0)
    try:
        client.connect(path)
        client.sendall(packet)
        response = json.loads(client.recv(4096).decode("utf-8"))
    finally:
        client.close()
    if response.get("request_id") != request_id or response.get("status") != "ok":
        raise AssertionError(f"unexpected activation response: {response!r}")
    return response


def main() -> int:
    if sys.platform != "linux":
        raise SystemExit("This probe requires Linux.")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime or not Path(runtime).is_dir():
        raise SystemExit("XDG_RUNTIME_DIR is unavailable; no files were created.")
    manager = run_systemctl("show-environment", check=False)
    if manager.returncode:
        raise SystemExit(
            "The systemd user manager is unavailable. Start no system services; "
            "run this probe from a session with a working systemctl --user bus."
        )

    token = f"{os.getpid()}-{secrets.token_hex(4)}"
    socket_unit = f"atlas-admin-ipc-probe-{token}.socket"
    service_unit = f"atlas-admin-ipc-probe-{token}.service"
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir_identities = _ensure_directory_chain(unit_dir)
    socket_unit_path = unit_dir / socket_unit
    service_unit_path = unit_dir / service_unit

    private_dir = Path(tempfile.mkdtemp(prefix="atlas-admin-ipc-probe-", dir=runtime))
    os.chmod(private_dir, 0o700)
    private_dir_identity = _path_identity(private_dir)
    socket_path = private_dir / "admin.sock"
    socket_identity = None
    uid = os.getuid()
    unit_file_identities: dict[Path, tuple[int, int, int]] = {}
    daemon_reloaded = False

    socket_contents = f"""[Unit]
Description=Temporary Atlas authority IPC activation probe {token}

[Socket]
ListenSequentialPacket={socket_path}
Service={service_unit}
Accept=no
SocketMode=0600
DirectoryMode=0700
RemoveOnStop=no
"""

    service_contents = f"""[Unit]
Description=Temporary Atlas authority IPC activated service probe {token}

[Service]
Type=oneshot
ExecStart={quote_unit(str(PYTHON))} {quote_unit(str(HELPER))}
Environment=PYTHONPATH={ROOT / "src"}
Environment=ATLAS_EXPECTED_UID={uid}
Environment=ATLAS_EXPECTED_SOCKET={socket_path}
"""

    try:
        unit_file_identities[socket_unit_path] = _create_exclusive_file(
            socket_unit_path, socket_contents
        )
        unit_file_identities[service_unit_path] = _create_exclusive_file(
            service_unit_path, service_contents
        )

        run_systemctl("daemon-reload")
        daemon_reloaded = True

        # The runtime directory was freshly created with mode 0700. Never
        # place a pre-existing object at the socket path: systemd 257.13 on
        # the development host altered a regular file at that path. Collision
        # behavior is documented as unsafe/unresolved and is not retested here.
        run_systemctl("start", socket_unit)
        wait_for(lambda: socket_path.exists(), "systemd-created socket path")
        info = socket_path.lstat()
        if not stat.S_ISSOCK(info.st_mode):
            raise AssertionError("systemd did not create a filesystem socket")
        socket_identity = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
        if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != uid:
            raise AssertionError(
                f"unexpected socket owner/mode: uid={info.st_uid}, "
                f"mode={stat.S_IMODE(info.st_mode):04o}"
            )
        if stat.S_IMODE(private_dir.stat().st_mode) != 0o700:
            raise AssertionError("private runtime directory mode changed")

        for activation_number in (1, 2):
            send_ping(str(socket_path))
            wait_for(
                lambda: active_state(service_unit) in {"inactive", "failed"},
                f"one-shot service activation {activation_number} to finish",
            )
            if active_state(service_unit) == "failed":
                raise AssertionError(f"activated service failed: {service_unit}")

        # The socket unit owns the pathname; the one-shot service must not unlink it.
        if not _identity_matches(socket_path, socket_identity, "socket"):
            raise AssertionError("activated service replaced or removed the systemd-owned socket")
        run_systemctl("stop", service_unit, check=False)
        run_systemctl("stop", socket_unit, check=False)
        if not _identity_matches(socket_path, socket_identity, "socket"):
            raise AssertionError("RemoveOnStop=no did not preserve the original socket object")
        print("PASS: systemd user socket activation, descriptor validation,")
        print("      two activations and private ownership/mode.")
        print("PASS: RemoveOnStop=no leaves pathname cleanup to the test harness.")
        return 0
    finally:
        run_systemctl("stop", service_unit, check=False)
        run_systemctl("stop", socket_unit, check=False)
        for unit_path, identity in unit_file_identities.items():
            if not _unlink_if_same_identity(unit_path, identity, "file"):
                print(
                    f"Refusing to remove a replaced or unexpected unit file: {unit_path}",
                    file=sys.stderr,
                )
        if daemon_reloaded:
            run_systemctl("daemon-reload", check=False)

        # A missing identity means systemd never created a socket we can safely
        # claim. In that case leave any unexpected object untouched for inspection.
        if not _unlink_if_same_identity(socket_path, socket_identity, "socket"):
            if socket_path.exists() or socket_path.is_symlink():
                print(
                    f"Refusing to remove a replaced or unexpected socket path: {socket_path}",
                    file=sys.stderr,
                )
        if not _rmdir_if_same_identity(private_dir, private_dir_identity):
            print(
                f"Manual inspection/cleanup may be needed for temporary directory: {private_dir}",
                file=sys.stderr,
            )
        for created_dir, identity in reversed(list(unit_dir_identities.items())):
            if not _rmdir_if_same_identity(created_dir, identity):
                print(
                    f"Leaving unit directory not owned by this invocation: {created_dir}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())
