#!/usr/bin/env python3
"""Opt-in, non-privileged A-IPC-01 private AF_UNIX listener probe.

This is an experiment only. It does not install services, touch SQLite, or
create a persistent Atlas listener. Run manually from the repository root.
"""
from __future__ import annotations

import argparse
import array
import base64
import hashlib
import errno
import json
import os
from pathlib import Path
import platform
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
READ_TIMEOUT = 0.35
WRITE_TIMEOUT = 0.35
MAX_ACTIVE_CONNECTIONS = 2
LISTEN_BACKLOG = 8
MAX_ACCEPT_WAIT_SECONDS = 8.0


class ProbeSkip(Exception):
    pass


class ProbeFailure(Exception):
    pass


def _require_collision_errno(value: int | None, scenario: str) -> None:
    if value not in (errno.EADDRINUSE, errno.EEXIST):
        raise ProbeFailure(f"{scenario}: unexpected bind-collision errno {value}")


def _identity(path: Path) -> tuple[int, int, int]:
    info = path.lstat()
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


def _describe(path: Path) -> dict[str, int]:
    info = path.lstat()
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "file_type": stat.S_IFMT(info.st_mode),
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
    }


class CaseSandbox:
    """A private per-scenario directory with identity-checked cleanup only."""

    def __init__(self, root: Path, name: str) -> None:
        self.path = root / name
        self.path.mkdir(mode=0o700)
        info = self.path.lstat()
        self.directory_identity = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
            raise ProbeFailure(f"{name}: scenario directory is not an exact 0700 directory")
        if info.st_uid != os.geteuid():
            raise ProbeFailure(f"{name}: scenario directory has unexpected owner")
        self.entries: list[tuple[Path, tuple[int, int, int]]] = []

    def track(self, path: Path) -> tuple[int, int, int]:
        identity = _identity(path)
        self.entries.append((path, identity))
        return identity

    def forget(self, path: Path, identity: tuple[int, int, int]) -> None:
        self.entries = [
            entry for entry in self.entries
            if not (entry[0] == path and entry[1] == identity)
        ]

    def cleanup(self) -> list[str]:
        problems: list[str] = []
        for path, expected in reversed(self.entries):
            try:
                current = _identity(path)
            except FileNotFoundError:
                continue
            except OSError as exc:
                problems.append(f"cannot inspect {path.name}: {exc}")
                continue
            if current != expected:
                problems.append(f"identity changed; preserved {path.name}")
                continue
            try:
                if stat.S_ISDIR(current[2]):
                    path.rmdir()
                else:
                    path.unlink()
            except OSError as exc:
                problems.append(f"cannot remove owned {path.name}: {exc}")
        try:
            if _identity(self.path) != self.directory_identity:
                problems.append("scenario directory identity changed; preserved")
            else:
                self.path.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            problems.append(f"scenario directory not empty or not removable: {exc}")
        return problems


class OwnedListener:
    """Listener pathname cleanup guarded by the captured lstat identity."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.identity: tuple[int, int, int] | None = None

    def bind_listen(self, backlog: int = 1) -> None:
        old_umask = os.umask(0o177)
        try:
            self.socket.bind(str(self.path))
        finally:
            os.umask(old_umask)
        info = self.path.lstat()
        if not stat.S_ISSOCK(info.st_mode):
            raise ProbeFailure("bind did not create a socket pathname")
        self.identity = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
        os.chmod(self.path, 0o600)
        info = self.path.lstat()
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise ProbeFailure("socket mode is not exactly 0600")
        self.socket.listen(backlog)

    def close_descriptor(self) -> None:
        self.socket.close()

    def cleanup_path(self) -> bool:
        """Close and unlink only if the current pathname is still ours."""
        if self.socket.fileno() != -1:
            self.socket.close()
        if self.identity is None:
            return False
        try:
            current = _identity(self.path)
        except FileNotFoundError:
            return True
        if current != self.identity or not stat.S_ISSOCK(current[2]):
            return False
        try:
            self.path.unlink()
        except OSError:
            return False
        return True


def _ping_packet() -> tuple[str, bytes]:
    request_id = str(uuid.uuid4())
    packet = json.dumps(
        {
            "protocol": "atlas-admin/1",
            "request_id": request_id,
            "operation": "authority.ping",
            "payload": {},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return request_id, packet


def _serve_one(connection: socket.socket) -> tuple[dict, object]:
    from atlas.platform_admin_ipc import handle_admin_connection

    peer, request = handle_admin_connection(
        connection,
        allowed_peer_uids={os.getuid()},
        read_timeout_seconds=READ_TIMEOUT,
        write_timeout_seconds=WRITE_TIMEOUT,
    )
    return peer, request


def _connect(path: Path, timeout: float = 1.0) -> socket.socket:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    client.settimeout(timeout)
    client.connect(str(path))
    return client


def _ping_exchange(listener: socket.socket, path: Path) -> dict[str, int]:
    listener.settimeout(MAX_ACCEPT_WAIT_SECONDS)
    request_id, packet = _ping_packet()
    with _connect(path) as client:
        client.sendall(packet)
        connection, _ = listener.accept()
        with connection:
            peer, request = _serve_one(connection)
        response = json.loads(client.recv(MAX_RESPONSE_BYTES).decode("utf-8"))
    if (
        response.get("protocol") != "atlas-admin/1"
        or response.get("request_id") != request_id
        or request.request_id != request_id
        or response.get("status") != "completed"
        or response.get("code") != "OK"
        or response.get("result", {}).get("handler_status") != "available"
    ):
        raise ProbeFailure(f"unexpected atlas-admin/1 ping response: {response!r}")
    return {"pid": peer.pid, "uid": peer.uid, "gid": peer.gid}


def _scenario_a01(root: Path) -> dict[str, object]:
    box = CaseSandbox(root, "a01")
    listener = OwnedListener(box.path / "s")
    try:
        listener.bind_listen()
        box.track(listener.path)
        info = listener.path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ProbeFailure("socket type/mode mismatch")
        if stat.S_IMODE(box.path.stat().st_mode) != 0o700:
            raise ProbeFailure("directory mode mismatch")
        listener.socket.settimeout(1.0)
        observed = {"directory_mode": stat.S_IMODE(box.path.stat().st_mode), "socket": _describe(listener.path)}
        client = _connect(listener.path)
        client.close()
        connection, _ = listener.socket.accept()
        connection.close()
        return observed
    finally:
        listener.socket.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a02(root: Path) -> dict[str, object]:
    box = CaseSandbox(root, "a02")
    path = box.path / "s"
    path.write_bytes(b"A-IPC-01-regular-sentinel")
    box.track(path)
    content = path.read_bytes()
    before = _describe(path)
    collision_errno = None
    contender = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        try:
            contender.bind(str(path))
        except OSError as exc:
            collision_errno = exc.errno
        else:
            raise ProbeFailure("bind unexpectedly replaced a regular file")
        _require_collision_errno(collision_errno, "A02")
        if _identity(path) != (before["device"], before["inode"], before["file_type"]) or path.read_bytes() != content:
            raise ProbeFailure("regular file changed after bind collision")
        return {"before": before, "after": _describe(path), "bind_errno": collision_errno, "sentinel_unchanged": True}
    finally:
        contender.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a03(root: Path) -> dict[str, object]:
    box = CaseSandbox(root, "a03")
    target = box.path / "target"
    target.write_bytes(b"A-IPC-01-symlink-target")
    target_id = box.track(target)
    path = box.path / "s"
    path.symlink_to(target)
    link_id = box.track(path)
    before_link, before_target = _describe(path), _describe(target)
    collision_errno = None
    contender = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        try:
            contender.bind(str(path))
        except OSError as exc:
            collision_errno = exc.errno
        else:
            raise ProbeFailure("bind unexpectedly replaced a symlink")
        _require_collision_errno(collision_errno, "A03")
        if _identity(path) != link_id or _identity(target) != target_id:
            raise ProbeFailure("symlink or target identity changed")
        if target.read_bytes() != b"A-IPC-01-symlink-target":
            raise ProbeFailure("symlink target content changed")
        return {"link_before": before_link, "link_after": _describe(path), "target_before": before_target, "target_after": _describe(target), "bind_errno": collision_errno}
    finally:
        contender.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a04(root: Path) -> dict[str, object]:
    box = CaseSandbox(root, "a04")
    path = box.path / "s"
    first = OwnedListener(path)
    second = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        first.bind_listen()
        first_id = box.track(path)
        before = _describe(path)
        collision_errno = None
        try:
            second.bind(str(path))
        except OSError as exc:
            collision_errno = exc.errno
        else:
            raise ProbeFailure("second bind unexpectedly succeeded")
        _require_collision_errno(collision_errno, "A04")
        if _identity(path) != first_id:
            raise ProbeFailure("second bind altered the first listener pathname")
        first.socket.settimeout(1.0)
        client = _connect(path)
        client.close()
        connection, _ = first.socket.accept()
        connection.close()
        return {"before": before, "after": _describe(path), "second_bind_errno": collision_errno, "winner_operational": True}
    finally:
        second.close()
        first.socket.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a05(root: Path) -> dict[str, object]:
    box = CaseSandbox(root, "a05")
    path = box.path / "s"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    stale.bind(str(path))
    stale.close()
    stale_id = box.track(path)
    before = _describe(path)
    collision_errno = None
    contender = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        try:
            contender.bind(str(path))
        except OSError as exc:
            collision_errno = exc.errno
        else:
            raise ProbeFailure("bind unexpectedly replaced a stale socket")
        _require_collision_errno(collision_errno, "A05")
        if _identity(path) != stale_id or not stat.S_ISSOCK(path.lstat().st_mode):
            raise ProbeFailure("stale socket pathname changed")
        return {"before": before, "after": _describe(path), "bind_errno": collision_errno, "stale_path_preserved": True}
    finally:
        contender.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a06(root: Path) -> dict[str, object]:
    box = CaseSandbox(root, "a06")
    path = box.path / "s"
    listener = OwnedListener(path)
    try:
        listener.bind_listen()
        original_id = box.track(path)
        listener.close_descriptor()
        path.unlink()
        box.forget(path, original_id)
        path.write_bytes(b"replacement-must-survive")
        replacement_id = box.track(path)
        if listener.cleanup_path():
            raise ProbeFailure("cleanup claimed ownership of a replacement pathname")
        if _identity(path) != replacement_id or path.read_bytes() != b"replacement-must-survive":
            raise ProbeFailure("cleanup modified the replacement object")
        return {"original_socket_identity": list(original_id), "replacement_identity": list(replacement_id), "replacement_preserved": True, "cleanup_reason": "CLEANUP_SKIPPED_OWNERSHIP_MISMATCH"}
    finally:
        listener.socket.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a07(root: Path) -> dict[str, object]:
    box = CaseSandbox(root, "a07")
    listener = OwnedListener(box.path / "s")
    try:
        listener.bind_listen()
        box.track(listener.path)
        if not listener.cleanup_path():
            raise ProbeFailure("cleanup did not remove the owned socket")
        if listener.path.exists() or os.path.lexists(listener.path):
            raise ProbeFailure("owned socket pathname remains after cleanup")
        return {"owned_socket_identity": list(listener.identity or ()), "owned_path_removed": True}
    finally:
        listener.socket.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a08(root: Path) -> dict[str, int]:
    box = CaseSandbox(root, "a08")
    listener = OwnedListener(box.path / "s")
    try:
        listener.bind_listen()
        box.track(listener.path)
        return _ping_exchange(listener.socket, listener.path)
    finally:
        listener.socket.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))



A09_ACCOUNT = "atlas-a09-test"
A09_HELPER_PATH = Path("/tmp/atlas-a09-client.py")
A09_EXPECTED_HOSTKEY = "SHA256:txiDPT+/ldcIwnN6BPotbeL7QsofAieAeqF3GKMa9xI"
A09_SSH_TIMEOUT_SECONDS = 10.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Opt-in A-IPC-01 private Unix listener probe")
    parser.add_argument(
        "--enable-a09",
        action="store_true",
        help="run A09a/A09b using the pre-provisioned, restricted SSH identity",
    )
    parser.add_argument("--a09-identity-file", type=Path)
    parser.add_argument("--a09-known-hosts", type=Path)
    args = parser.parse_args()
    if args.enable_a09 and (args.a09_identity_file is None or args.a09_known_hosts is None):
        parser.error("--enable-a09 requires --a09-identity-file and --a09-known-hosts")
    if not args.enable_a09 and (args.a09_identity_file is not None or args.a09_known_hosts is not None):
        parser.error("A09 key paths require --enable-a09")
    return args


def _regular_owned_file(path: Path, *, mode: int, uid: int, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ProbeSkip(f"{label} cannot be inspected: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != mode:
        raise ProbeSkip(f"{label} must be a regular file owned by UID {uid} with mode {mode:04o}")
    return info


def _a09_config(args: argparse.Namespace) -> dict[str, object]:
    import pwd

    if not args.enable_a09:
        raise ProbeSkip("A09a/A09b disabled; pass --enable-a09 after host-side helper authorization")
    if os.geteuid() == 0:
        raise ProbeSkip("A09 requires the ordinary checkout UID")
    try:
        account = pwd.getpwnam(A09_ACCOUNT)
    except KeyError as exc:
        raise ProbeSkip(f"required external account {A09_ACCOUNT} is unavailable") from exc
    if account.pw_uid in (0, os.geteuid()):
        raise ProbeSkip("external peer UID must be non-root and different from the runner UID")

    identity_file = args.a09_identity_file.expanduser().absolute()
    known_hosts = args.a09_known_hosts.expanduser().absolute()
    try:
        key_parent = identity_file.parent.lstat()
    except OSError as exc:
        raise ProbeSkip(f"A09 private-key directory cannot be inspected: {exc}") from exc
    if (
        not stat.S_ISDIR(key_parent.st_mode)
        or key_parent.st_uid != os.geteuid()
        or stat.S_IMODE(key_parent.st_mode) != 0o700
    ):
        raise ProbeSkip("A09 private-key directory must be owned by the runner with mode 0700")
    key_info = _regular_owned_file(identity_file, mode=0o600, uid=os.geteuid(), label="A09 private key")
    hosts_info = _regular_owned_file(known_hosts, mode=0o600, uid=os.geteuid(), label="A09 known_hosts")
    if key_info.st_nlink != 1 or hosts_info.st_nlink != 1:
        raise ProbeSkip("A09 key and known_hosts must not be hard-linked files")

    try:
        tmp_info = Path("/tmp").lstat()
    except OSError as exc:
        raise ProbeSkip(f"/tmp cannot be inspected: {exc}") from exc
    if (
        not stat.S_ISDIR(tmp_info.st_mode)
        or tmp_info.st_uid != 0
        or stat.S_IMODE(tmp_info.st_mode) != 0o1777
    ):
        raise ProbeSkip("/tmp must be a real root-owned directory with exact mode 01777")

    try:
        known_text = known_hosts.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProbeSkip(f"A09 known_hosts cannot be read: {exc}") from exc
    pinned_keys: list[str] = []
    for line in known_text.splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) >= 3 and fields[0] == "[127.0.0.1]:22" and fields[1] == "ssh-ed25519":
            pinned_keys.append(fields[2])
    if len(pinned_keys) != 1:
        raise ProbeSkip("A09 known_hosts must contain exactly one explicit [127.0.0.1]:22 ED25519 entry")
    try:
        key_blob = base64.b64decode(pinned_keys[0], validate=True)
    except ValueError as exc:
        raise ProbeSkip("A09 known_hosts ED25519 key encoding is invalid") from exc
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key_blob).digest()).decode("ascii").rstrip("=")
    if fingerprint != A09_EXPECTED_HOSTKEY:
        raise ProbeSkip("A09 known_hosts loopback ED25519 key differs from the previously verified fingerprint")

    return {
        "username": A09_ACCOUNT,
        "peer_uid": account.pw_uid,
        "peer_gid": account.pw_gid,
        "identity_file": identity_file,
        "known_hosts": known_hosts,
    }


def _install_a09_helper() -> tuple[Path, tuple[int, int, int]]:
    try:
        tmp_info = Path("/tmp").lstat()
    except OSError as exc:
        raise ProbeSkip(f"/tmp cannot be inspected: {exc}") from exc
    if (
        not stat.S_ISDIR(tmp_info.st_mode)
        or tmp_info.st_uid != 0
        or stat.S_IMODE(tmp_info.st_mode) != 0o1777
    ):
        raise ProbeSkip("/tmp failed the exact root-owned 01777 precondition")
    source = Path(__file__).with_name("a09_ssh_client.py")
    source_info = source.lstat()
    if not stat.S_ISREG(source_info.st_mode):
        raise ProbeFailure("A09 helper source is not a regular file")
    content = source.read_bytes()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(A09_HELPER_PATH, flags, 0o644)
    except FileExistsError as exc:
        raise ProbeSkip("fixed A09 helper path already exists; preserved without modification") from exc
    opened = os.fstat(fd)
    identity = (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode))
    try:
        os.fchmod(fd, 0o644)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o644:
            raise ProbeFailure("temporary A09 helper has unexpected type, owner or mode")
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise ProbeFailure("short write while installing temporary A09 helper")
            view = view[written:]
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            current = A09_HELPER_PATH.lstat()
            current_identity = (current.st_dev, current.st_ino, stat.S_IFMT(current.st_mode))
            if current_identity == identity and stat.S_ISREG(current.st_mode) and current.st_uid == os.geteuid():
                A09_HELPER_PATH.unlink()
        except OSError:
            pass
        raise
    else:
        os.close(fd)
    current = A09_HELPER_PATH.lstat()
    if (
        (current.st_dev, current.st_ino, stat.S_IFMT(current.st_mode)) != identity
        or not stat.S_ISREG(current.st_mode)
        or current.st_uid != os.geteuid()
        or stat.S_IMODE(current.st_mode) != 0o644
    ):
        try:
            current_identity = (current.st_dev, current.st_ino, stat.S_IFMT(current.st_mode))
            if current_identity == identity and stat.S_ISREG(current.st_mode) and current.st_uid == os.geteuid():
                A09_HELPER_PATH.unlink()
        except OSError:
            pass
        raise ProbeFailure("temporary A09 helper identity changed during installation")
    return A09_HELPER_PATH, identity


def _remove_a09_helper(path: Path, identity: tuple[int, int, int]) -> None:
    try:
        current = path.lstat()
    except FileNotFoundError:
        raise ProbeFailure("temporary A09 helper disappeared before cleanup")
    if (
        (current.st_dev, current.st_ino, stat.S_IFMT(current.st_mode)) != identity
        or not stat.S_ISREG(current.st_mode)
        or current.st_uid != os.geteuid()
        or stat.S_IMODE(current.st_mode) != 0o644
    ):
        raise ProbeFailure("temporary A09 helper identity changed; preserved")
    path.unlink()


def _start_a09_ssh(
    config: dict[str, object],
    scenario: str,
    socket_path: Path,
    helper_path: Path,
) -> tuple[subprocess.Popen[bytes], threading.Thread, dict[str, object]]:
    if helper_path != A09_HELPER_PATH:
        raise ProbeFailure("A09 helper path differs from the fixed forced-command target")
    nonce = uuid.uuid4().hex
    instruction = json.dumps(
        {"scenario": scenario, "socket_path": str(socket_path), "nonce": nonce},
        separators=(",", ":"),
    ).encode("utf-8")
    command = [
        "/usr/bin/ssh",
        "-F", "/dev/null",
        "-T",
        "-o", "RequestTTY=no",
        "-p", "22",
        "-i", str(config["identity_file"]),
        "-o", "IdentitiesOnly=yes",
        "-o", "IdentityAgent=none",
        "-o", "PubkeyAuthentication=yes",
        "-o", "GSSAPIAuthentication=no",
        "-o", "HostbasedAuthentication=no",
        "-o", "BatchMode=yes",
        "-o", "PreferredAuthentications=publickey",
        "-o", "PasswordAuthentication=no",
        "-o", "KbdInteractiveAuthentication=no",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={config['known_hosts']}",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "HostKeyAlgorithms=ssh-ed25519",
        "-o", "PubkeyAcceptedAlgorithms=ssh-ed25519",
        "-o", "ConnectTimeout=5",
        "-o", "ConnectionAttempts=1",
        "-o", "ControlMaster=no",
        "-o", "ControlPath=none",
        "-o", "ProxyCommand=none",
        "-o", "ProxyJump=none",
        "-o", "ForwardAgent=no",
        "-o", "ForwardX11=no",
        "-o", "ClearAllForwardings=yes",
        "-o", "PermitLocalCommand=no",
        "-o", "UpdateHostKeys=no",
        f"{config['username']}@127.0.0.1",
    ]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except OSError as exc:
        raise ProbeSkip(f"cannot start the fixed local SSH client: {exc}") from exc
    outcome: dict[str, object] = {"nonce": nonce}

    def communicate() -> None:
        try:
            stdout, stderr = process.communicate(instruction, timeout=A09_SSH_TIMEOUT_SECONDS)
            outcome.update({"stdout": stdout, "stderr": stderr, "returncode": process.returncode})
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            outcome.update({
                "stdout": stdout,
                "stderr": stderr,
                "returncode": process.returncode,
                "timeout": True,
            })
        except BaseException as exc:
            outcome["exception"] = f"{type(exc).__name__}: {exc}"

    worker = threading.Thread(target=communicate, name=f"{scenario}-ssh", daemon=True)
    worker.start()
    return process, worker, outcome


def _finish_a09_ssh(
    process: subprocess.Popen[bytes],
    worker: threading.Thread,
    outcome: dict[str, object],
) -> dict[str, object]:
    worker.join(timeout=A09_SSH_TIMEOUT_SECONDS + 2.0)
    if worker.is_alive():
        process.kill()
        worker.join(timeout=2.0)
    if worker.is_alive():
        raise ProbeFailure("A09 SSH communication worker did not terminate after child kill")
    if "exception" in outcome:
        raise ProbeFailure(f"A09 SSH communication failed: {outcome['exception']}")
    if outcome.get("timeout"):
        raise ProbeFailure("A09 SSH client exceeded its 10-second total timeout")
    if outcome.get("returncode") != 0:
        stderr = outcome.get("stderr", b"")
        detail = stderr.decode("utf-8", errors="replace")[:500] if isinstance(stderr, bytes) else ""
        raise ProbeFailure(f"A09 SSH client exited unsuccessfully: {detail or outcome.get('returncode')}")
    stdout = outcome.get("stdout")
    stderr = outcome.get("stderr")
    if not isinstance(stdout, bytes) or len(stdout) > 4096 or not isinstance(stderr, bytes):
        raise ProbeFailure("A09 SSH helper output exceeded its bounded format")
    if stderr:
        raise ProbeFailure("A09 SSH emitted unexpected stderr output")
    try:
        lines = stdout.decode("ascii", errors="strict").splitlines()
        if len(lines) != 1:
            raise ValueError("expected exactly one JSON line")
        report = json.loads(lines[0])
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ProbeFailure(f"A09 SSH helper returned invalid JSON: {exc}") from exc
    if not isinstance(report, dict):
        raise ProbeFailure("A09 SSH helper result is not a JSON object")
    if report.get("nonce") != outcome["nonce"]:
        raise ProbeFailure("A09 SSH helper nonce mismatch")
    return report


def _validate_a09_client_identity(report: dict[str, object], config: dict[str, object], scenario: str) -> None:
    if report.get("scenario") != scenario:
        raise ProbeFailure(f"{scenario}: SSH helper reported a different scenario")
    if report.get("uid") != config["peer_uid"] or report.get("gid") != config["peer_gid"]:
        raise ProbeFailure(f"{scenario}: SSH helper credentials do not match the provisioned peer")
    if not isinstance(report.get("pid"), int) or report["pid"] <= 0:
        raise ProbeFailure(f"{scenario}: SSH helper did not report a valid PID")


def _scenario_a09a(root: Path, config: dict[str, object] | None, skip_reason: str | None) -> dict[str, object]:
    if config is None:
        raise ProbeSkip(skip_reason or "A09 SSH preflight is unavailable")
    box = CaseSandbox(root, "a09a")
    listener = OwnedListener(box.path / "s")
    helper_path = None
    helper_identity = None
    process = None
    worker = None
    outcome = None
    try:
        listener.bind_listen()
        box.track(listener.path)
        listener.socket.settimeout(MAX_ACCEPT_WAIT_SECONDS)
        helper_path, helper_identity = _install_a09_helper()
        process, worker, outcome = _start_a09_ssh(config, "A09a", listener.path, helper_path)
        worker.join(timeout=A09_SSH_TIMEOUT_SECONDS + 2.0)
        if worker.is_alive():
            process.kill()
            worker.join(timeout=2.0)
        if worker.is_alive():
            raise ProbeFailure("A09a SSH worker did not terminate")
        report = _finish_a09_ssh(process, worker, outcome)
        _validate_a09_client_identity(report, config, "A09a")
        if report.get("connected") is not False or report.get("connect_errno") != errno.EACCES:
            raise ProbeFailure(f"A09a expected DAC EACCES, got {report!r}")
        listener.socket.settimeout(0.25)
        try:
            unexpected, _ = listener.socket.accept()
        except TimeoutError:
            pass
        else:
            unexpected.close()
            raise ProbeFailure("A09a listener accepted a connection despite expected DAC denial")
        if _identity(listener.path) != listener.identity:
            raise ProbeFailure("A09a candidate socket identity changed")
        info = listener.path.lstat()
        if stat.S_IMODE(info.st_mode) != 0o600 or stat.S_IMODE(box.path.stat().st_mode) != 0o700:
            raise ProbeFailure("A09a candidate endpoint permissions changed")
        return {
            "peer_uid": report["uid"],
            "peer_gid": report["gid"],
            "peer_pid": report["pid"],
            "connect_errno": report["connect_errno"],
            "accepted_connections": 0,
            "candidate_socket": _describe(listener.path),
            "directory_mode": stat.S_IMODE(box.path.stat().st_mode),
        }
    finally:
        cleanup_errors: list[str] = []
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except OSError as exc:
                cleanup_errors.append(f"cannot terminate A09a SSH child: {exc}")
        if worker is not None:
            worker.join(timeout=2.0)
            if worker.is_alive():
                cleanup_errors.append("A09a SSH worker remained active after child termination")
        listener.socket.close()
        if helper_path is not None and helper_identity is not None:
            try:
                _remove_a09_helper(helper_path, helper_identity)
            except Exception as exc:
                cleanup_errors.append(f"A09a helper cleanup failed: {type(exc).__name__}: {exc}")
        cleanup_errors.extend(box.cleanup())
        if cleanup_errors:
            raise ProbeFailure("; ".join(cleanup_errors))


def _scenario_a09b(root: Path, config: dict[str, object] | None, skip_reason: str | None) -> dict[str, object]:
    if config is None:
        raise ProbeSkip(skip_reason or "A09 SSH preflight is unavailable")
    tmp = Path("/tmp")
    try:
        tmp_info = tmp.lstat()
    except OSError as exc:
        raise ProbeSkip(f"/tmp cannot be inspected: {exc}") from exc
    if (
        not stat.S_ISDIR(tmp_info.st_mode)
        or tmp_info.st_uid != 0
        or stat.S_IMODE(tmp_info.st_mode) != 0o1777
    ):
        raise ProbeSkip("/tmp is not a verified root-owned sticky directory")
    try:
        fixture = Path(tempfile.mkdtemp(prefix="atlas-a09b-", dir=str(tmp)))
    except OSError as exc:
        raise ProbeSkip(f"cannot create the isolated A09b fixture under /tmp: {exc}") from exc
    fixture_info = fixture.lstat()
    fixture_identity = (fixture_info.st_dev, fixture_info.st_ino, stat.S_IFMT(fixture_info.st_mode))
    try:
        listener = OwnedListener(fixture / "s")
    except OSError as exc:
        fixture.rmdir()
        raise ProbeSkip(f"cannot create A09b listener socket: {exc}") from exc
    helper_path = None
    helper_identity = None
    process = None
    worker = None
    outcome = None
    try:
        if (
            not stat.S_ISDIR(fixture_info.st_mode)
            or fixture_info.st_uid != os.geteuid()
            or stat.S_IMODE(fixture_info.st_mode) != 0o700
        ):
            raise ProbeFailure("A09b fixture was not created as an owned 0700 directory")
        os.chmod(fixture, 0o711)
        if stat.S_IMODE(fixture.lstat().st_mode) != 0o711:
            raise ProbeFailure("A09b fixture directory mode is not exactly 0711")
        listener.bind_listen()
        os.chmod(listener.path, 0o666)
        info = listener.path.lstat()
        if (
            not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o666
        ):
            raise ProbeFailure("A09b fixture socket type, owner or mode mismatch")
        listener.socket.settimeout(MAX_ACCEPT_WAIT_SECONDS)
        helper_path, helper_identity = _install_a09_helper()
        process, worker, outcome = _start_a09_ssh(config, "A09b", listener.path, helper_path)
        try:
            connection, _ = listener.socket.accept()
        except TimeoutError as exc:
            raise ProbeFailure("A09b external peer did not reach the fixture listener") from exc
        from atlas.platform_admin_ipc import AdminPeerRejected, read_peer_credentials

        with connection:
            peer = read_peer_credentials(connection)
            if (
                peer.uid != config["peer_uid"]
                or peer.gid != config["peer_gid"]
                or peer.uid == os.getuid()
            ):
                raise ProbeFailure("A09b kernel SO_PEERCRED UID/GID does not match the external test identity")
            try:
                _serve_one(connection)
            except AdminPeerRejected as exc:
                if exc.code != "UNAUTHORIZED_PEER":
                    raise ProbeFailure(f"A09b handler returned unexpected rejection {exc.code}") from exc
            else:
                raise ProbeFailure("A09b handler did not reject the external peer")
        report = _finish_a09_ssh(process, worker, outcome)
        _validate_a09_client_identity(report, config, "A09b")
        if report.get("pid") != peer.pid:
            raise ProbeFailure("A09b helper PID does not match kernel SO_PEERCRED PID")
        if (
            report.get("connected") is not True
            or report.get("connect_errno") is not None
            or report.get("peer_closed") is not True
            or not isinstance(report.get("request_bytes_sent"), int)
            or report.get("request_bytes_sent", 0) <= 0
            or report.get("bytes_received") != 0
            or report.get("closure") not in {"eof", "reset"}
        ):
            raise ProbeFailure(f"A09b peer received data or did not observe server closure: {report!r}")
        if _identity(listener.path) != listener.identity:
            raise ProbeFailure("A09b fixture socket identity changed before cleanup")
        fixture_mode = stat.S_IMODE(fixture.lstat().st_mode)
        socket_mode = stat.S_IMODE(listener.path.lstat().st_mode)
        if fixture_mode != 0o711 or socket_mode != 0o666:
            raise ProbeFailure("A09b fixture permissions changed during the exchange")
        return {
            "peer_pid": peer.pid,
            "peer_uid": peer.uid,
            "peer_gid": peer.gid,
            "handler_rejection": "UNAUTHORIZED_PEER",
            "response_bytes": report["bytes_received"],
            "client_observed_closure": report["closure"],
            "fixture_directory_mode": fixture_mode,
            "fixture_socket_mode": socket_mode,
            "request_bytes_sent": report["request_bytes_sent"],
        }
    finally:
        cleanup_errors: list[str] = []
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except OSError as exc:
                cleanup_errors.append(f"cannot terminate A09b SSH child: {exc}")
        if worker is not None:
            worker.join(timeout=2.0)
            if worker.is_alive():
                cleanup_errors.append("A09b SSH worker remained active after child termination")
        listener.socket.close()
        if listener.identity is not None:
            try:
                current = _identity(listener.path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                cleanup_errors.append(f"cannot inspect A09b fixture socket: {exc}")
            else:
                if current == listener.identity and stat.S_ISSOCK(current[2]):
                    try:
                        listener.path.unlink()
                    except OSError as exc:
                        cleanup_errors.append(f"cannot remove owned A09b fixture socket: {exc}")
                else:
                    cleanup_errors.append("A09b fixture socket identity changed; preserved")
        if helper_path is not None and helper_identity is not None:
            try:
                _remove_a09_helper(helper_path, helper_identity)
            except Exception as exc:
                cleanup_errors.append(f"A09b helper cleanup failed: {type(exc).__name__}: {exc}")
        try:
            current_dir = fixture.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            cleanup_errors.append(f"cannot inspect A09b fixture directory: {exc}")
        else:
            current_identity = (current_dir.st_dev, current_dir.st_ino, stat.S_IFMT(current_dir.st_mode))
            if current_identity != fixture_identity or not stat.S_ISDIR(current_dir.st_mode):
                cleanup_errors.append("A09b fixture directory identity changed; preserved")
            else:
                try:
                    fixture.rmdir()
                except OSError as exc:
                    cleanup_errors.append(f"cannot remove empty A09b fixture directory: {exc}")
        if cleanup_errors:
            raise ProbeFailure("; ".join(cleanup_errors))


def _scenario_a10(root: Path) -> dict[str, int]:
    box = CaseSandbox(root, "a10")
    listener = OwnedListener(box.path / "s")
    try:
        listener.bind_listen()
        box.track(listener.path)
        peer = _ping_exchange(listener.socket, listener.path)
        if peer["uid"] != os.getuid():
            raise ProbeFailure("kernel-reported peer UID did not match the authorized UID")
        return peer
    finally:
        listener.socket.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a11(root: Path) -> None:
    from atlas.platform_admin_ipc import AdminPeerDisconnected

    box = CaseSandbox(root, "a11")
    listener = OwnedListener(box.path / "s")
    try:
        listener.bind_listen()
        box.track(listener.path)
        listener.socket.settimeout(1.0)
        client = _connect(listener.path)
        connection, _ = listener.socket.accept()
        client.close()
        with connection:
            try:
                _serve_one(connection)
            except AdminPeerDisconnected:
                pass
            else:
                raise ProbeFailure("disconnect before request was not rejected")
    finally:
        listener.socket.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a12(root: Path) -> None:
    from atlas.platform_admin_ipc import AdminProtocolRejected

    for name, send in (
        ("truncated", "truncated"),
        ("ancillary", "ancillary"),
    ):
        box = CaseSandbox(root, "a12-" + name)
        listener = OwnedListener(box.path / "s")
        read_fd, write_fd = os.pipe()
        try:
            listener.bind_listen()
            box.track(listener.path)
            listener.socket.settimeout(1.0)
            client = _connect(listener.path)
            connection, _ = listener.socket.accept()
            with client, connection:
                if send == "truncated":
                    client.sendall(b"x" * (MAX_REQUEST_BYTES + 4096))
                else:
                    rights = array.array("i", [read_fd])
                    client.sendmsg([b"ancillary-forbidden"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)])
                try:
                    _serve_one(connection)
                except AdminProtocolRejected as exc:
                    expected = "MESSAGE_TRUNCATED" if send == "truncated" else "ANCILLARY_DATA_FORBIDDEN"
                    if exc.code != expected:
                        raise ProbeFailure(f"{name}: unexpected rejection code {exc.code}")
                else:
                    raise ProbeFailure(f"{name}: invalid packet was accepted")
                client.settimeout(0.15)
                try:
                    response = client.recv(1024)
                except TimeoutError:
                    response = b""
                if response:
                    raise ProbeFailure(f"{name}: handler sent a forbidden error response")
        finally:
            os.close(read_fd)
            os.close(write_fd)
            listener.socket.close()
            errors = box.cleanup()
            if errors:
                raise ProbeFailure("; ".join(errors))


def _scenario_a13(root: Path) -> None:
    from atlas.platform_admin_ipc import AdminIPCError

    box = CaseSandbox(root, "a13")
    listener = OwnedListener(box.path / "s")
    try:
        listener.bind_listen()
        box.track(listener.path)
        listener.socket.settimeout(1.0)
        client = _connect(listener.path)
        connection, _ = listener.socket.accept()
        with client, connection:
            started = time.monotonic()
            try:
                _serve_one(connection)
            except AdminIPCError as exc:
                if exc.code != "TIMEOUT":
                    raise ProbeFailure(f"expected TIMEOUT, got {exc.code}")
            else:
                raise ProbeFailure("idle peer did not time out")
            if time.monotonic() - started > MAX_ACCEPT_WAIT_SECONDS:
                raise ProbeFailure("read timeout exceeded scenario bound")
    finally:
        listener.socket.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


class BoundedAcceptHarness:
    """Small test-only accept loop with a fixed worker ceiling."""

    def __init__(self, listener: socket.socket) -> None:
        self.listener = listener
        self.slots = threading.BoundedSemaphore(MAX_ACTIVE_CONNECTIONS)
        self.stop_event = threading.Event()
        self.paused = threading.Event()
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.rejected = 0
        self.handled = 0
        self.threads: list[threading.Thread] = []
        self.worker_release = threading.Event()
        self.worker_errors: list[str] = []
        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)

    def start(self) -> None:
        self.listener.settimeout(0.1)
        self.accept_thread.start()

    def _accept_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.paused.is_set():
                time.sleep(0.01)
                continue
            try:
                connection, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with self.lock:
                self.handled += 1
            if not self.slots.acquire(blocking=False):
                with self.lock:
                    self.rejected += 1
                connection.close()
                continue
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            thread = threading.Thread(target=self._worker, args=(connection,), daemon=True)
            self.threads.append(thread)
            thread.start()

    def _worker(self, connection: socket.socket) -> None:
        try:
            # Hold admitted workers until the test has filled the bounded
            # capacity. This makes saturation independent of scheduler speed
            # and the handler's read timeout.
            if not self.worker_release.wait(timeout=MAX_ACCEPT_WAIT_SECONDS):
                with self.lock:
                    self.worker_errors.append("worker release gate timed out")
                return
            try:
                _serve_one(connection)
            except Exception as exc:
                from atlas.platform_admin_ipc import AdminIPCError

                if not isinstance(exc, AdminIPCError) or exc.code not in {
                    "TIMEOUT",
                    "PEER_DISCONNECTED",
                }:
                    with self.lock:
                        self.worker_errors.append(
                            f"{type(exc).__name__}: {exc}"
                        )
        finally:
            try:
                connection.close()
            finally:
                with self.lock:
                    self.active -= 1
                self.slots.release()

    def wait_idle(self, timeout: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if self.active == 0:
                    return True
            time.sleep(0.02)
        return False

    def close(self) -> None:
        self.stop_event.set()
        self.worker_release.set()
        self.listener.close()
        self.accept_thread.join(timeout=1.0)
        for thread in self.threads:
            thread.join(timeout=1.0)


def _scenario_a14(root: Path) -> dict[str, int]:
    box = CaseSandbox(root, "a14")
    listener = OwnedListener(box.path / "s")
    harness = None
    clients: list[socket.socket] = []
    try:
        listener.bind_listen(backlog=LISTEN_BACKLOG)
        box.track(listener.path)
        harness = BoundedAcceptHarness(listener.socket)
        harness.start()
        for _ in range(8):
            try:
                clients.append(_connect(listener.path, timeout=0.5))
            except OSError:
                pass
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            with harness.lock:
                if harness.handled >= len(clients):
                    break
            time.sleep(0.02)
        with harness.lock:
            if harness.handled != len(clients):
                raise ProbeFailure("not all connected clients were accepted by the harness")
            if harness.active != MAX_ACTIVE_CONNECTIONS:
                raise ProbeFailure("saturation did not occupy the full worker ceiling")
            if harness.peak > MAX_ACTIVE_CONNECTIONS:
                raise ProbeFailure("active connection count exceeded the fixed worker ceiling")
            if harness.rejected < 1:
                raise ProbeFailure("saturation did not exercise controlled rejection")
        harness.worker_release.set()
        for client in clients:
            client.close()
        clients.clear()
        if not harness.wait_idle():
            raise ProbeFailure("worker capacity did not recover after clients closed")
        with harness.lock:
            if harness.worker_errors:
                raise ProbeFailure(
                    "bounded worker reported unexpected errors: "
                    + "; ".join(harness.worker_errors)
                )
        harness.paused.set()
        time.sleep(0.15)
        request_id, packet = _ping_packet()
        with _connect(listener.path) as client:
            client.sendall(packet)
            connection, _ = listener.socket.accept()
            with connection:
                _peer, request = _serve_one(connection)
            response = json.loads(client.recv(MAX_RESPONSE_BYTES).decode("utf-8"))
        if (
            response.get("request_id") != request_id
            or request.request_id != request_id
            or response.get("status") != "completed"
            or response.get("code") != "OK"
        ):
            raise ProbeFailure("listener did not recover to process a valid ping")
        with harness.lock:
            return {"peak_active": harness.peak, "rejected_connections": harness.rejected, "handled_connections": harness.handled, "active_after_recovery": harness.active}
    finally:
        for client in clients:
            client.close()
        if harness is not None:
            harness.close()
        else:
            listener.socket.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a15(root: Path) -> None:
    box = CaseSandbox(root, "a15")
    path = box.path / "s"
    listener = OwnedListener(path)
    try:
        listener.bind_listen()
        box.track(path)
        listener.socket.close()
        if listener.cleanup_path() is False:
            raise ProbeFailure("cleanup unexpectedly refused its own unchanged socket")
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            try:
                probe.connect(str(path))
            except OSError:
                pass
            else:
                raise ProbeFailure("connection succeeded after listener shutdown")
        finally:
            probe.close()
    finally:
        listener.socket.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


def _scenario_a16(root: Path) -> dict[str, object]:
    box = CaseSandbox(root, "a16")
    path = box.path / "s"
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    outcomes: list[tuple[str, socket.socket, int | None]] = []

    def contender() -> None:
        candidate = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            barrier.wait(timeout=2.0)
            candidate.bind(str(path))
            with lock:
                outcomes.append(("won", candidate, None))
        except OSError as exc:
            with lock:
                outcomes.append(("lost", candidate, exc.errno))
        except BaseException:
            candidate.close()
            raise

    threads = [threading.Thread(target=contender) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3.0)
        if any(thread.is_alive() for thread in threads):
            raise ProbeFailure("concurrent bind contender did not finish")
        winners = [item for item in outcomes if item[0] == "won"]
        losers = [item for item in outcomes if item[0] == "lost"]
        if len(winners) != 1 or len(losers) != 1:
            raise ProbeFailure(f"expected one bind winner and one loser, got {len(winners)}/{len(losers)}")
        if losers[0][2] not in (errno.EADDRINUSE, errno.EEXIST):
            raise ProbeFailure(f"losing bind returned unexpected errno {losers[0][2]}")
        winner = winners[0][1]
        info = path.lstat()
        winner_id = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
        box.track(path)
        os.chmod(path, 0o600)
        if stat.S_IMODE(path.lstat().st_mode) != 0o600:
            raise ProbeFailure("winning socket mode is not exactly 0600")
        winner.listen(1)
        winner.settimeout(1.0)
        request_id, packet = _ping_packet()
        client = _connect(path)
        client.sendall(packet)
        connection, _ = winner.accept()
        with client, connection:
            _serve_one(connection)
            response = json.loads(client.recv(MAX_RESPONSE_BYTES).decode("utf-8"))
        if (
            response.get("request_id") != request_id
            or response.get("status") != "completed"
            or response.get("code") != "OK"
        ):
            raise ProbeFailure("winning listener did not remain operational")
        if _identity(path) != winner_id:
            raise ProbeFailure("winner pathname identity changed during loser collision")
        return {"winner_identity": list(winner_id), "loser_errno": losers[0][2], "winner_operational": True}
    finally:
        for _state, candidate, _error in outcomes:
            candidate.close()
        errors = box.cleanup()
        if errors:
            raise ProbeFailure("; ".join(errors))


SCENARIOS = [
    ("A01", "private bind/listen/accept/close", _scenario_a01),
    ("A02", "regular-file collision is non-destructive", _scenario_a02),
    ("A03", "symlink and target survive collision", _scenario_a03),
    ("A04", "second bind cannot replace active listener", _scenario_a04),
    ("A05", "stale socket is not auto-removed", _scenario_a05),
    ("A06", "cleanup preserves a replacement pathname", _scenario_a06),
    ("A07", "cleanup removes the unchanged owned socket", _scenario_a07),
    ("A08", "allowed peer completes atlas-admin/1 ping", _scenario_a08),
    ("A09a", "different-UID peer is denied by candidate endpoint DAC", None),
    ("A09b", "real SO_PEERCRED rejects an external peer without response", None),
    ("A10", "allowed peer identity is read from kernel credentials", _scenario_a10),
    ("A11", "disconnect before request is controlled", _scenario_a11),
    ("A12", "truncation and ancillary data are rejected silently", _scenario_a12),
    ("A13", "idle peer is released by read timeout", _scenario_a13),
    ("A14", "bounded workers reject excess and recover capacity", _scenario_a14),
    ("A15", "closed listener no longer accepts connections", _scenario_a15),
    ("A16", "two concurrent binds have exactly one winner", _scenario_a16),
]


def _preflight() -> tuple[Path, tuple[int, int, int]]:
    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        raise ProbeSkip("Linux AF_UNIX/SO_PEERCRED is required")
    if not hasattr(os, "geteuid") or os.geteuid() == 0:
        raise ProbeSkip("run as an ordinary unprivileged user; UID 0 is refused")
    temp_base = Path(tempfile.gettempdir()).absolute()
    cursor = Path(temp_base.anchor)
    for component in temp_base.parts[1:]:
        cursor = cursor / component
        info = cursor.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ProbeSkip(f"temporary path component is not a real directory: {cursor}")
    root = Path(tempfile.mkdtemp(prefix="atlas-aipc01-"))
    info = root.lstat()
    identity = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.geteuid()
    ):
        try:
            root.rmdir()
        except OSError:
            pass
        raise ProbeSkip("temporary sandbox failed exact owner/type/mode preconditions")
    socket_probe = root / "a12-ancillary" / "s"
    if len(os.fsencode(socket_probe)) >= 100:
        root.rmdir()
        raise ProbeSkip("temporary path is too long for the AF_UNIX pathname limit")
    return root, identity


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> int:
    args = _parse_args()
    try:
        from atlas.platform_admin_ipc import PROTOCOL_ID
        if PROTOCOL_ID != "atlas-admin/1":
            raise ProbeSkip("checkout handler does not expose atlas-admin/1")
        root, root_identity = _preflight()
    except ProbeSkip as exc:
        print(json.dumps({"overall": "INCOMPLETE", "reason": str(exc)}, indent=2))
        return 2

    a09_config = None
    a09_skip_reason = None
    if args.enable_a09:
        try:
            a09_config = _a09_config(args)
        except ProbeSkip as exc:
            a09_skip_reason = str(exc)
    else:
        a09_skip_reason = "A09a/A09b disabled; explicit --enable-a09 and approved host forced-command setup are required"

    results: list[dict[str, object]] = []
    started = time.monotonic()
    try:
        for case_id, description, function in SCENARIOS:
            case_started = time.monotonic()
            observations = None
            try:
                if case_id == "A09a":
                    observations = _scenario_a09a(root, a09_config, a09_skip_reason)
                elif case_id == "A09b":
                    observations = _scenario_a09b(root, a09_config, a09_skip_reason)
                else:
                    observations = function(root)
            except ProbeSkip as exc:
                status, detail = "SKIP", str(exc)
            except Exception as exc:
                status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
            else:
                status, detail = "PASS", "completed"
            scenario_result = {
                "id": case_id,
                "description": description,
                "status": status,
                "detail": detail,
                "duration_seconds": f"{time.monotonic() - case_started:.3f}",
            }
            if observations is not None:
                scenario_result["observations"] = observations
            results.append(scenario_result)
            if status == "FAIL":
                break
    finally:
        try:
            if _identity(root) != root_identity:
                cleanup_detail = "sandbox root identity changed; preserved"
            else:
                root.rmdir()
                cleanup_detail = "empty sandbox root removed"
        except OSError as exc:
            cleanup_detail = f"sandbox root preserved: {exc}"

    statuses = {item["status"] for item in results}
    overall = "FAIL" if "FAIL" in statuses else ("INCOMPLETE" if "SKIP" in statuses else "PASS")
    if cleanup_detail != "empty sandbox root removed":
        overall = "FAIL"
    report = {
        "probe": "A-IPC-01",
        "overall": overall,
        "commit": _git_commit(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "effective_uid": os.geteuid(),
        "a09_enabled": args.enable_a09,
        "a09_peer_account": A09_ACCOUNT if a09_config is not None else None,
        "a09_peer_uid": a09_config["peer_uid"] if a09_config is not None else None,
        "sandbox_root": str(root),
        "limits": {
            "request_bytes": MAX_REQUEST_BYTES,
            "response_bytes": MAX_RESPONSE_BYTES,
            "read_timeout_seconds": READ_TIMEOUT,
            "write_timeout_seconds": WRITE_TIMEOUT,
            "listen_backlog": LISTEN_BACKLOG,
            "max_active_connections": MAX_ACTIVE_CONNECTIONS,
            "max_accept_wait_seconds": MAX_ACCEPT_WAIT_SECONDS,
        },
        "duration_seconds": round(time.monotonic() - started, 3),
        "cleanup": cleanup_detail,
        "scenarios": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if overall == "PASS" else (1 if overall == "FAIL" else 2)


if __name__ == "__main__":
    raise SystemExit(main())