#!/usr/bin/env python3
"""Opt-in, non-privileged A-IPC-01 private AF_UNIX listener probe.

This is an experiment only. It does not install services, touch SQLite, or
create a persistent Atlas listener. Run manually from the repository root.
"""
from __future__ import annotations

import array
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


def _scenario_a09(root: Path) -> None:
    raise ProbeSkip(
        "multi-UID peer test not run: the probe will not change UID/GID, use sudo, "
        "or assume a second pre-existing identity"
    )


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
            if not self.worker_release.wait(timeout=2.0):
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
    ("A09", "different-UID peer rejection (conditional)", _scenario_a09),
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
    try:
        from atlas.platform_admin_ipc import PROTOCOL_ID
        if PROTOCOL_ID != "atlas-admin/1":
            raise ProbeSkip("checkout handler does not expose atlas-admin/1")
        root, root_identity = _preflight()
    except ProbeSkip as exc:
        print(json.dumps({"overall": "INCOMPLETE", "reason": str(exc)}, indent=2))
        return 2

    results: list[dict[str, object]] = []
    started = time.monotonic()
    try:
        for case_id, description, function in SCENARIOS:
            case_started = time.monotonic()
            observations = None
            try:
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