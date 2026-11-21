#!/usr/bin/env python3
"""Root-only, disposable-VM probe for mutual SO_PEERCRED auth and bounded IPC.

This is an isolated experiment. It does not install services, touch SQLite,
modify host accounts, or create a persistent Atlas listener.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import errno
import json
import os
from pathlib import Path
import platform
import resource
import queue
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

WORKERS = 4
BACKLOG = 8
READ_TIMEOUT = 5.0
WRITE_TIMEOUT = 5.0
GLOBAL_DEADLINE = 15.0
REQUEST_LIMIT = 16 * 1024
RESPONSE_LIMIT = 64 * 1024
FD_LIMIT = 64
SS_BIN = shutil.which("ss")
_EMIT_LOCK = threading.Lock()


class ProbeIncomplete(Exception):
    pass


class ProbeFailure(Exception):
    pass


def emit(**event: object) -> None:
    with _EMIT_LOCK:
        print(json.dumps(event, sort_keys=True), flush=True)


def _request_packet() -> tuple[str, bytes]:
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


def _serve_authenticated(
    connection: socket.socket, allowed_uid: int, accepted_at: float
) -> None:
    """Fixture handler: authenticate before recv and enforce one global deadline."""
    from atlas.platform_admin_ipc import (
        AdminProtocolRejected,
        MAX_REQUEST_BYTES,
        PROTOCOL_ID,
        _encode_response,
        _service_version,
        decode_admin_request,
        read_peer_credentials,
    )

    peer = read_peer_credentials(connection)
    if peer.uid != allowed_uid:
        emit(
            event="unauthorized_peer",
            peer_uid=peer.uid,
            peer_pid=peer.pid,
            recv_started=False,
            response_sent=False,
        )
        return

    deadline = accepted_at + GLOBAL_DEADLINE
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        emit(event="deadline_before_read", peer_uid=peer.uid)
        return

    connection.settimeout(min(READ_TIMEOUT, remaining))
    try:
        packet, ancillary, flags, _address = connection.recvmsg(MAX_REQUEST_BYTES + 1)
    except TimeoutError:
        emit(event="read_timeout", peer_uid=peer.uid)
        return

    if not packet:
        emit(event="request_eof", peer_uid=peer.uid, bytes_received=0)
        return
    if ancillary or flags & getattr(socket, "MSG_CTRUNC", 0):
        emit(event="ancillary_rejected", peer_uid=peer.uid)
        return
    if flags & getattr(socket, "MSG_TRUNC", 0):
        emit(event="truncated_rejected", peer_uid=peer.uid)
        return

    try:
        request = decode_admin_request(packet)
    except AdminProtocolRejected as exc:
        emit(
            event="request_rejected",
            peer_uid=peer.uid,
            code=exc.code,
            request_id=exc.request_id,
        )
        return
    if request.operation != "authority.ping":
        raise ProbeFailure("fixture received an operation other than authority.ping")

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        emit(event="deadline_before_write", peer_uid=peer.uid)
        return
    response = _encode_response(
        {
            "protocol": PROTOCOL_ID,
            "request_id": request.request_id,
            "status": "completed",
            "code": "OK",
            "summary": "Operation completed",
            "result": {
                "protocol_version": PROTOCOL_ID,
                "service_version": _service_version(),
                "handler_status": "available",
            },
            "audit_ref": None,
        }
    )
    if len(response) > RESPONSE_LIMIT:
        raise ProbeFailure("fixture response exceeded configured response limit")
    connection.settimeout(min(WRITE_TIMEOUT, remaining))
    sent = connection.send(response)
    if sent != len(response):
        raise ProbeFailure("SOCK_SEQPACKET response was not sent atomically")
    emit(event="request_completed", peer_uid=peer.uid, bytes_received=len(packet))


def _server_child(socket_path: str, socket_mode: int, allowed_uid: int) -> int:
    global _STOP
    _STOP = threading.Event()
    listener: socket.socket | None = None
    socket_identity: tuple[int, int, int] | None = None
    lock = threading.Lock()
    active = 0
    max_active = 0
    max_workers = 0
    accepted = 0
    slots = threading.BoundedSemaphore(WORKERS)

    from atlas.platform_admin_ipc import (
        MAX_JSON_DEPTH,
        MAX_REQUEST_BYTES,
        MAX_RESPONSE_BYTES,
    )
    if (
        MAX_REQUEST_BYTES != REQUEST_LIMIT
        or MAX_RESPONSE_BYTES != RESPONSE_LIMIT
        or MAX_JSON_DEPTH != 16
        or allowed_uid != 0
    ):
        emit(event="startup_error", reason="handler limits or root client policy differ from approved probe profile")
        return 3

    uid = os.getuid()
    gid = os.getgid()
    if os.getresuid() != (uid, uid, uid) or os.getresgid() != (gid, gid, gid):
        emit(event="startup_error", reason="real/effective/saved UID/GID mismatch")
        return 3
    if os.getgroups():
        emit(event="startup_error", reason="supplementary groups are not empty")
        return 3

    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if hard < FD_LIMIT:
        emit(event="startup_error", reason="hard RLIMIT_NOFILE is below 64", hard=hard)
        return 3
    resource.setrlimit(resource.RLIMIT_NOFILE, (FD_LIMIT, FD_LIMIT))

    def stop(_signum: int, _frame: object) -> None:
        _STOP.set()
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    target = Path(socket_path)
    try:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        old_umask = os.umask(0o177)
        try:
            listener.bind(socket_path)
        finally:
            os.umask(old_umask)
        info = target.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != uid:
            raise ProbeFailure("listener pathname has unexpected type or owner")
        socket_identity = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
        os.chmod(socket_path, socket_mode)
        if stat.S_IMODE(target.lstat().st_mode) != socket_mode:
            raise ProbeFailure("listener pathname mode differs from fixture policy")
        listener.listen(BACKLOG)
        listener.settimeout(0.2)
        emit(
            event="ready",
            pid=os.getpid(),
            uid=uid,
            gid=gid,
            socket_mode=oct(socket_mode),
            workers=WORKERS,
            backlog=BACKLOG,
            read_timeout=READ_TIMEOUT,
            write_timeout=WRITE_TIMEOUT,
            global_deadline=GLOBAL_DEADLINE,
            rlimit_nofile=resource.getrlimit(resource.RLIMIT_NOFILE)[0],
            socket_identity=list(socket_identity),
        )

        def worker(connection: socket.socket, accepted_at: float) -> None:
            nonlocal active, max_active, max_workers
            with lock:
                active += 1
                max_active = max(max_active, active)
                max_workers = max(max_workers, active)
                emit(event="metrics", active=active, max_active=max_active,
                     max_workers=max_workers, accepted=accepted)
            try:
                with connection:
                    _serve_authenticated(connection, allowed_uid, accepted_at)
            except Exception as exc:
                emit(event="worker_error", error=f"{type(exc).__name__}: {exc}")
            finally:
                with lock:
                    active -= 1
                    emit(event="metrics", active=active, max_active=max_active,
                         max_workers=max_workers, accepted=accepted)
                slots.release()

        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            while not _STOP.is_set():
                slots.acquire()
                if _STOP.is_set():
                    slots.release()
                    break
                try:
                    connection, _address = listener.accept()
                except socket.timeout:
                    slots.release()
                    continue
                except OSError:
                    slots.release()
                    if _STOP.is_set():
                        break
                    raise
                with lock:
                    accepted += 1
                    current_accepted = accepted
                emit(event="accepted", accepted=current_accepted)
                try:
                    pool.submit(worker, connection, time.monotonic())
                except Exception:
                    connection.close()
                    slots.release()
                    raise
    except Exception as exc:
        emit(event="server_error", error=f"{type(exc).__name__}: {exc}")
        return 1
    finally:
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
        if socket_identity is not None:
            try:
                current = target.lstat()
                identity = (current.st_dev, current.st_ino, stat.S_IFMT(current.st_mode))
                if identity == socket_identity and stat.S_ISSOCK(current.st_mode):
                    target.unlink()
                else:
                    emit(event="cleanup_preserved", reason="socket pathname identity changed")
            except FileNotFoundError:
                pass
            except OSError as exc:
                emit(event="cleanup_error", error=str(exc))
    emit(event="stopped")
    return 0


def _client_child(socket_path: str) -> int:
    request_id, packet = _request_packet()
    client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    client.settimeout(2.0)
    try:
        client.connect(socket_path)
        try:
            client.send(packet)
        except OSError:
            # A fast pre-recv rejection may close the peer before send reaches
            # the socket; the server-side evidence remains authoritative.
            pass
        try:
            response = client.recv(RESPONSE_LIMIT)
        except OSError:
            response = b""
        emit(event="unprivileged_client_result", request_id=request_id,
             response_bytes=len(response))
        return 0 if not response else 1
    finally:
        client.close()


def _forged_identity_packet() -> bytes:
    """Build a valid ping envelope with untrusted identity claims added."""
    request_id = str(uuid.uuid4())
    return json.dumps(
        {
            "protocol": "atlas-admin/1",
            "request_id": request_id,
            "operation": "authority.ping",
            "payload": {},
            "uid": 0,
            "gid": 0,
            "pid": 1,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _negative_euid_client_child(socket_path: str) -> int:
    """Exercise the privileged-client EUID guard before any socket is created."""
    euid = os.geteuid()
    if euid == 0:
        emit(event="negative_client_fixture_error", reason="fixture unexpectedly has EUID 0")
        return 3
    try:
        _connect_as_root(Path(socket_path), expected_server_uid=0, send_request=False)
    except ProbeFailure as exc:
        expected = "privileged client fixture must have EUID 0"
        if str(exc) != expected:
            emit(event="negative_client_unexpected_rejection", euid=euid, reason=str(exc))
            return 1
        emit(
            event="euid_rejected_before_connect",
            euid=euid,
            connect_attempted=False,
        )
        return 0
    emit(event="euid_guard_bypassed", euid=euid)
    return 1


class Server:
    def __init__(self, process: subprocess.Popen[str], socket_path: Path) -> None:
        self.process = process
        self.socket_path = socket_path
        self.socket_identity: tuple[int, int, int] | None = None
        self.events: list[dict[str, object]] = []
        self._output: queue.Queue[object] = queue.Queue()
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        if self.process.stdout is None:
            self._output.put(("reader_error", "server stdout is unavailable"))
            self._output.put(None)
            return
        try:
            for line in self.process.stdout:
                try:
                    self._output.put(json.loads(line))
                except json.JSONDecodeError:
                    self._output.put(("parse_error", line.rstrip()))
        except Exception as exc:
            self._output.put(("reader_error", f"{type(exc).__name__}: {exc}"))
        finally:
            self._output.put(None)

    def _record(self, item: object) -> dict[str, object]:
        if item is None:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise ProbeFailure(f"server output closed unexpectedly: {stderr}")
        if isinstance(item, tuple):
            raise ProbeFailure(f"server output reader failed: {item}")
        if not isinstance(item, dict):
            raise ProbeFailure(f"server emitted invalid event type: {type(item).__name__}")
        self.events.append(item)
        if item.get("event") in {
            "startup_error", "server_error", "worker_error",
            "cleanup_error", "cleanup_preserved",
        }:
            raise ProbeFailure(f"server reported {item}")
        return item

    def next_event(self, timeout: float = 3.0) -> dict[str, object]:
        try:
            item = self._output.get(timeout=timeout)
        except queue.Empty as exc:
            raise ProbeFailure("timed out waiting for server evidence") from exc
        return self._record(item)

    def drain(self, duration: float) -> None:
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            try:
                item = self._output.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                return
            self._record(item)

    def wait_event(self, name: str, predicate=None, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        for event in self.events:
            if event.get("event") == name and (predicate is None or predicate(event)):
                return event
        while time.monotonic() < deadline:
            event = self.next_event(max(0.05, deadline - time.monotonic()))
            if event.get("event") == name and (predicate is None or predicate(event)):
                return event
        raise ProbeFailure(f"did not observe server event {name}")

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=8.0)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2.0)
            raise ProbeFailure("server did not stop within bounded shutdown wait")
        self._reader.join(timeout=2.0)
        if self._reader.is_alive():
            raise ProbeFailure("server output reader did not reach EOF after process exit")
        while True:
            try:
                item = self._output.get_nowait()
            except queue.Empty:
                break
            if item is None:
                continue
            self._record(item)
        if self.process.returncode != 0:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise ProbeFailure(f"server exited {self.process.returncode}: {stderr}")
        try:
            current = self.socket_path.lstat()
        except FileNotFoundError:
            return
        identity = (current.st_dev, current.st_ino, stat.S_IFMT(current.st_mode))
        if (
            self.socket_identity is None
            or identity != self.socket_identity
            or not stat.S_ISSOCK(current.st_mode)
        ):
            raise ProbeFailure("socket pathname changed; preserving sandbox for inspection")
        self.socket_path.unlink()


def _start_server(
    script: Path,
    socket_path: Path,
    uid: int,
    gid: int,
    socket_mode: int,
    allowed_uid: int,
    registry: list[Server],
) -> Server:
    process = subprocess.Popen(
        [
            sys.executable, str(script), "--server-child",
            "--socket", str(socket_path),
            "--socket-mode", str(socket_mode),
            "--allowed-uid", str(allowed_uid),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        user=uid,
        group=gid,
        extra_groups=[],
    )
    server = Server(process, socket_path)
    registry.append(server)
    ready = server.wait_event("ready", timeout=5.0)
    identity = ready.get("socket_identity")
    if not isinstance(identity, list) or len(identity) != 3:
        raise ProbeFailure("server did not report its bound socket identity")
    server.socket_identity = (int(identity[0]), int(identity[1]), int(identity[2]))
    if ready.get("uid") != uid or ready.get("gid") != gid:
        raise ProbeFailure("server child did not retain the requested fixture identity")
    if ready.get("rlimit_nofile") != FD_LIMIT:
        raise ProbeFailure("server RLIMIT_NOFILE is not exactly 64")
    return server


def _connect_as_root(path: Path, expected_server_uid: int, *, send_request: bool):
    from atlas.platform_admin_ipc import read_peer_credentials

    if os.geteuid() != 0:
        raise ProbeFailure("privileged client fixture must have EUID 0")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    client.settimeout(2.0)
    client.connect(str(path))
    peer = read_peer_credentials(client)
    if peer.uid != expected_server_uid:
        client.close()
        if send_request:
            raise ProbeFailure("internal misuse: request send requested for wrong server")
        return peer, None
    if not send_request:
        client.close()
        return peer, None
    request_id, packet = _request_packet()
    sent = client.send(packet)
    if sent != len(packet):
        client.close()
        raise ProbeFailure("request packet was not sent atomically")
    response = client.recv(RESPONSE_LIMIT)
    client.close()
    decoded = json.loads(response.decode("utf-8"))
    if decoded.get("request_id") != request_id or decoded.get("code") != "OK":
        raise ProbeFailure("authenticated server returned an invalid ping response")
    return peer, decoded


def _wait_metrics(
    server: Server,
    *,
    active: int,
    accepted_at_least: int = 0,
    timeout: float = 4.0,
):
    return server.wait_event(
        "metrics",
        predicate=lambda item: (
            item.get("active") == active
            and int(item.get("accepted", 0)) >= accepted_at_least
        ),
        timeout=timeout,
    )


def _preflight(args: argparse.Namespace) -> tuple[Path, Path]:
    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        raise ProbeIncomplete("Linux AF_UNIX/SO_PEERCRED is required")
    if os.geteuid() != 0 or os.getresuid() != (0, 0, 0):
        raise ProbeIncomplete("run directly as root inside the disposable VM")
    if not args.confirm_disposable_vm or not args.confirm_fixture_ids:
        raise ProbeIncomplete("both explicit disposable-VM and fixture-ID confirmations are required")
    ids = (args.service_uid, args.service_gid, args.other_uid, args.other_gid)
    if any(value <= 0 for value in ids):
        raise ProbeIncomplete("fixture UID/GID values must be positive numeric IDs")
    if args.service_uid == args.other_uid:
        raise ProbeIncomplete("service and alternate fixture UIDs must differ")
    if args.service_gid == args.other_gid:
        raise ProbeIncomplete("service and alternate fixture GIDs must differ")
    if SS_BIN is None:
        raise ProbeIncomplete("iproute2 ss is required for exact kernel backlog observation")
    try:
        ss_info = Path(SS_BIN).resolve(strict=True).stat()
    except OSError as exc:
        raise ProbeIncomplete(f"cannot validate ss executable: {exc}") from exc
    if (
        not stat.S_ISREG(ss_info.st_mode)
        or ss_info.st_uid != 0
        or stat.S_IMODE(ss_info.st_mode) & 0o022
        or not os.access(SS_BIN, os.X_OK)
    ):
        raise ProbeIncomplete("ss executable must be a root-owned regular file not writable by group/others")
    run_dir = Path("/run")
    info = run_dir.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise ProbeIncomplete("/run must be a real root-owned directory not writable by group/others")
    tempfile = __import__("tempfile")
    root: Path | None = None
    public_root: Path | None = None
    try:
        root = Path(tempfile.mkdtemp(prefix="atlas-mutual-auth-", dir="/run"))
        public_root = Path(tempfile.mkdtemp(prefix="atlas-mutual-auth-public-", dir="/run"))
        os.chmod(root, 0o700)
        os.chmod(public_root, 0o711)
        info = root.lstat()
        public_info = public_root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
            raise ProbeFailure("private /run sandbox failed owner/type/mode validation")
        if (
            not stat.S_ISDIR(public_info.st_mode)
            or public_info.st_uid != 0
            or stat.S_IMODE(public_info.st_mode) != 0o711
            or public_info.st_mode & 0o022
        ):
            raise ProbeFailure("public traversal fixture root failed owner/type/mode validation")
        return root, public_root
    except Exception:
        for candidate in (public_root, root):
            if candidate is not None:
                try:
                    info = candidate.lstat()
                    if stat.S_ISDIR(info.st_mode) and info.st_uid == 0:
                        shutil.rmtree(candidate)
                except OSError:
                    pass
        raise


def _stage_probe_runtime(public_root: Path) -> Path:
    """Stage read-only source copies reachable by dropped-UID fixture children."""
    stage_root = public_root / "probe-runtime"
    package_dir = stage_root / "src" / "atlas"
    script_dir = stage_root / "tests" / "integration" / "private_unix_listener"
    for directory in (
        stage_root,
        stage_root / "src",
        package_dir,
        stage_root / "tests",
        stage_root / "tests" / "integration",
        script_dir,
    ):
        directory.mkdir(mode=0o755, exist_ok=True)
        os.chmod(directory, 0o755)
    source_module_dir = ROOT / "src" / "atlas"
    shutil.copyfile(source_module_dir / "platform_admin_ipc.py", package_dir / "platform_admin_ipc.py")
    init_file = source_module_dir / "__init__.py"
    if init_file.exists():
        shutil.copyfile(init_file, package_dir / "__init__.py")
        os.chmod(package_dir / "__init__.py", 0o644)
    os.chmod(package_dir / "platform_admin_ipc.py", 0o644)
    staged_script = script_dir / Path(__file__).name
    shutil.copyfile(Path(__file__).resolve(), staged_script)
    os.chmod(staged_script, 0o644)
    return staged_script


def _create_fixture_dir(path: Path, uid: int, gid: int, mode: int) -> None:
    path.mkdir(mode=mode)
    os.chown(path, uid, gid)
    os.chmod(path, mode)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_gid != gid:
        raise ProbeFailure(f"fixture directory identity mismatch: {path}")
    if stat.S_IMODE(info.st_mode) != mode or info.st_mode & 0o022:
        raise ProbeFailure(f"fixture directory permissions mismatch: {path}")


def _scenario_mutual_auth(
    public_root: Path,
    args: argparse.Namespace,
    script: Path,
    registry: list[Server],
) -> dict:
    service_dir = public_root / "auth-service"
    wrong_server_dir = public_root / "wrong-server"
    _create_fixture_dir(service_dir, args.service_uid, args.service_gid, 0o711)
    _create_fixture_dir(wrong_server_dir, args.other_uid, args.other_gid, 0o700)
    service_socket = service_dir / "admin.sock"
    wrong_socket = wrong_server_dir / "admin.sock"

    server = _start_server(
        script, service_socket, args.service_uid, args.service_gid, 0o666, 0, registry
    )
    try:
        negative_client = subprocess.run(
            [
                sys.executable, str(script), "--negative-client-child",
                "--socket", str(service_socket),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5.0,
            check=False,
            user=args.other_uid,
            group=args.other_gid,
            extra_groups=[],
        )
        if negative_client.returncode != 0:
            raise ProbeFailure(
                f"non-root client did not reject before connect: {negative_client.stderr}"
            )
        try:
            negative_result = json.loads(negative_client.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise ProbeFailure("non-root client emitted no valid EUID-guard evidence") from exc
        if (
            negative_result.get("event") != "euid_rejected_before_connect"
            or negative_result.get("euid") != args.other_uid
            or negative_result.get("connect_attempted") is not False
        ):
            raise ProbeFailure(f"unexpected EUID-negative client evidence: {negative_result}")
        server.drain(0.25)
        if any(
            item.get("event") in {"accepted", "unauthorized_peer"}
            for item in server.events
        ):
            raise ProbeFailure("server observed a connection from the EUID-negative client")
        negative_euid = {
            "client_euid": negative_result["euid"],
            "connect_attempted": False,
            "server_observed_connection": False,
        }

        forged_packet = _forged_identity_packet()
        forged_client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        forged_client.settimeout(2.0)
        try:
            forged_client.connect(str(service_socket))
            sent = forged_client.send(forged_packet)
            if sent != len(forged_packet):
                raise ProbeFailure("forged-identity packet was not sent atomically")
            forged_client.shutdown(socket.SHUT_WR)
        finally:
            forged_client.close()
        forged_rejection = server.wait_event(
            "request_rejected",
            predicate=lambda item: (
                item.get("peer_uid") == 0
                and item.get("code") == "INVALID_REQUEST"
            ),
            timeout=3.0,
        )
        if forged_rejection.get("request_id") is None:
            raise ProbeFailure("forged identity rejection did not retain the canonical request ID")
        forged_identity = {
            "claimed_uid": 0,
            "claimed_gid": 0,
            "claimed_pid": 1,
            "kernel_peer_uid": forged_rejection["peer_uid"],
            "rejection_code": forged_rejection["code"],
        }

        peer, response = _connect_as_root(service_socket, args.service_uid, send_request=True)
        if peer.uid != args.service_uid or response is None:
            raise ProbeFailure("valid root client did not authenticate the service")
        valid = {"server_uid": peer.uid, "request_id": response["request_id"]}

        wrong_server = _start_server(
            script, wrong_socket, args.other_uid, args.other_gid, 0o600, 0, registry
        )
        try:
            peer, _response = _connect_as_root(wrong_socket, args.service_uid, send_request=False)
            if peer.uid != args.other_uid:
                raise ProbeFailure("wrong-server fixture did not expose its actual kernel UID")
            wrong_server.wait_event(
                "request_eof",
                predicate=lambda item: item.get("bytes_received") == 0,
                timeout=3.0,
            )
            rejected_server = {"observed_uid": peer.uid, "bytes_sent_by_client": 0}
        finally:
            wrong_server.stop()

        child = subprocess.run(
            [
                sys.executable, str(script), "--client-child",
                "--socket", str(service_socket),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5.0,
            check=False,
            user=args.other_uid,
            group=args.other_gid,
            extra_groups=[],
        )
        if child.returncode != 0:
            raise ProbeFailure(f"unprivileged client fixture failed: {child.stderr}")
        client_result = json.loads(child.stdout.strip().splitlines()[-1])
        if client_result.get("response_bytes") != 0:
            raise ProbeFailure("server returned protocol bytes to an unauthorized client")
        server.wait_event(
            "unauthorized_peer",
            predicate=lambda item: (
                item.get("peer_uid") == args.other_uid
                and item.get("recv_started") is False
                and item.get("response_sent") is False
            ),
            timeout=3.0,
        )
        return {
            "nonroot_client_rejected_before_connect": negative_euid,
            "forged_identity_fields_rejected": forged_identity,
            "valid_root_client": valid,
            "wrong_server_rejected_before_send": rejected_server,
            "wrong_client_rejected_before_recv": {
                "peer_uid": args.other_uid,
                "response_bytes": 0,
            },
        }
    finally:
        server.stop()


def _unix_listener_queue(socket_path: Path) -> tuple[int, int]:
    """Read Linux AF_UNIX listener queue occupancy through iproute2 ss."""
    if SS_BIN is None:
        raise ProbeIncomplete("iproute2 ss is required to observe the kernel AF_UNIX backlog")
    try:
        result = subprocess.run(
            [SS_BIN, "-x", "-l", "-n", "-H"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeIncomplete(f"could not inspect AF_UNIX listener queues: {type(exc).__name__}") from exc
    if result.returncode != 0:
        raise ProbeIncomplete(f"ss could not inspect AF_UNIX listener queues: {result.stderr.strip()}")
    expected_path = str(socket_path)
    matches: list[tuple[int, int]] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[1] != "LISTEN" or fields[4] != expected_path:
            continue
        try:
            matches.append((int(fields[2]), int(fields[3])))
        except ValueError as exc:
            raise ProbeFailure(f"ss returned non-numeric queue counters: {line!r}") from exc
    if len(matches) != 1:
        raise ProbeFailure(
            f"expected one ss LISTEN row for {expected_path}, observed {len(matches)}"
        )
    return matches[0]


def _scenario_backlog(server: Server, socket_path: Path) -> dict:
    """Fill all workers and the kernel backlog, then prove overflow is rejected."""
    active_clients: list[socket.socket] = []
    queued_clients: list[socket.socket] = []
    overflow: socket.socket | None = None
    accepted_before = max(
        (
            int(item.get("accepted", 0))
            for item in server.events
            if item.get("event") == "accepted"
        ),
        default=0,
    )
    try:
        for _ in range(WORKERS):
            client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            client.settimeout(2.0)
            client.connect(str(socket_path))
            active_clients.append(client)
        _wait_metrics(server, active=WORKERS, accepted_at_least=accepted_before + WORKERS)

        for _ in range(BACKLOG):
            client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            client.settimeout(2.0)
            client.connect(str(socket_path))
            queued_clients.append(client)

        recv_q, send_q = _unix_listener_queue(socket_path)
        if (recv_q, send_q) != (BACKLOG, BACKLOG):
            raise ProbeFailure(
                f"kernel backlog did not reach the configured bound: "
                f"Recv-Q={recv_q}, Send-Q={send_q}, expected {BACKLOG}/{BACKLOG}"
            )

        server.drain(0.15)
        accepted_while_full = max(
            (
                int(item.get("accepted", 0))
                for item in server.events
                if item.get("event") == "accepted"
            ),
            default=0,
        )
        active_max = max(
            (
                int(item.get("max_active", 0))
                for item in server.events
                if item.get("event") == "metrics"
            ),
            default=0,
        )
        if accepted_while_full != accepted_before + WORKERS:
            raise ProbeFailure("server accepted a queued connection while all worker slots were occupied")
        if active_max > WORKERS:
            raise ProbeFailure("worker count exceeded the fixed capacity during backlog saturation")

        overflow = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        overflow.setblocking(False)
        overflow_result = overflow.connect_ex(str(socket_path))
        if overflow_result not in {errno.EAGAIN, errno.EWOULDBLOCK}:
            raise ProbeFailure(
                f"connection beyond full kernel backlog was not rejected with EAGAIN: "
                f"connect_ex={overflow_result}"
            )

        recv_q_after, send_q_after = _unix_listener_queue(socket_path)
        if (recv_q_after, send_q_after) != (BACKLOG, BACKLOG):
            raise ProbeFailure(
                f"overflow attempt changed the full kernel backlog: "
                f"Recv-Q={recv_q_after}, Send-Q={send_q_after}"
            )
        server.drain(0.15)
        accepted_after_overflow = max(
            (
                int(item.get("accepted", 0))
                for item in server.events
                if item.get("event") == "accepted"
            ),
            default=0,
        )
        if accepted_after_overflow != accepted_before + WORKERS:
            raise ProbeFailure("overflow attempt caused an additional application accept")

        return {
            "configured_kernel_backlog": BACKLOG,
            "active_workers_at_saturation": WORKERS,
            "accepted_before_saturation": accepted_before,
            "accepted_while_full": accepted_while_full,
            "kernel_recv_q": recv_q,
            "kernel_send_q": send_q,
            "overflow_connect_errno": overflow_result,
            "kernel_recv_q_after_overflow": recv_q_after,
            "kernel_send_q_after_overflow": send_q_after,
            "accepted_after_overflow": accepted_after_overflow,
            "worker_limit_respected": active_max <= WORKERS,
        }
    finally:
        if overflow is not None:
            overflow.close()
        for client in queued_clients + active_clients:
            try:
                client.close()
            except OSError:
                pass


def _scenario_capacity(server: Server, socket_path: Path) -> dict:
    clients: list[socket.socket] = []
    try:
        for _ in range(WORKERS):
            client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            client.settimeout(2.0)
            client.connect(str(socket_path))
            clients.append(client)
        first = _wait_metrics(server, active=WORKERS)
        fifth = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        fifth.settimeout(2.0)
        fifth.connect(str(socket_path))
        clients.append(fifth)
        server.drain(0.25)
        accepted_while_full = [
            int(item.get("accepted", 0))
            for item in server.events
            if item.get("event") == "accepted"
        ]
        metrics_while_full = [
            int(item.get("max_active", 0))
            for item in server.events
            if item.get("event") == "metrics"
        ]
        observed_max = max(metrics_while_full or [int(first.get("max_active", 0))])
        if observed_max > WORKERS or max(accepted_while_full or [0]) > WORKERS:
            raise ProbeFailure("a fifth connection was accepted while all worker slots were occupied")
        for client in clients[:WORKERS]:
            client.close()
        server.wait_event(
            "accepted",
            predicate=lambda item: int(item.get("accepted", 0)) >= WORKERS + 1,
            timeout=5.0,
        )
        _wait_metrics(
            server, active=1, accepted_at_least=WORKERS + 1, timeout=5.0
        )
        clients[WORKERS].close()
        clients = []
        final = _wait_metrics(
            server, active=0, accepted_at_least=WORKERS + 1, timeout=5.0
        )
        max_active = max(
            [int(item.get("max_active", 0)) for item in server.events if item.get("event") == "metrics"]
        )
        max_workers = max(
            [int(item.get("max_workers", 0)) for item in server.events if item.get("event") == "metrics"]
        )
        if max_active > WORKERS or max_workers > WORKERS:
            raise ProbeFailure("fixed worker/active connection bound was exceeded")
        return {
            "configured_workers": WORKERS,
            "configured_kernel_backlog": BACKLOG,
            "observed_max_active": max_active,
            "observed_max_workers": max_workers,
            "active_after_recovery": final.get("active"),
            "backlog_saturation": "not tested; kernel backlog is configured but not filled",
        }
    finally:
        for client in clients:
            try:
                client.close()
            except OSError:
                pass


def _scenario_configuration(root: Path, args: argparse.Namespace) -> tuple[dict, dict]:
    """Exercise strict fixture loading (MA-07) and immutable snapshots (MA-08)."""
    from probe_config import ProbeConfigRejected, load_probe_config_at, parse_probe_config

    config_dir = root / "config-fixtures"
    config_dir.mkdir(mode=0o700)
    os.chmod(config_dir, 0o700)
    directory_fd = os.open(
        config_dir,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    created: set[str] = set()

    def write_fixture(
        name: str,
        data: bytes,
        *,
        mode: int = 0o644,
        uid: int = 0,
        gid: int = 0,
    ) -> None:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            mode,
            dir_fd=directory_fd,
        )
        created.add(name)
        try:
            os.fchown(descriptor, uid, gid)
            os.fchmod(descriptor, mode)
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise ProbeFailure("short write while creating config fixture")
                view = view[written:]
        finally:
            os.close(descriptor)

    def base_config(
        *,
        service_uid: int | None = None,
        service_gid: int | None = None,
        socket_path: str = "/run/atlas/admin.sock",
    ) -> bytes:
        uid = args.service_uid if service_uid is None else service_uid
        gid = args.service_gid if service_gid is None else service_gid
        return (
            "schema_version=1\n"
            f"service_uid={uid}\n"
            f"service_gid={gid}\n"
            "client_uids=0\n"
            f"socket_path={socket_path}\n"
            "socket_type=SOCK_SEQPACKET\n"
            "socket_mode=0600\n"
            "socket_dir_mode=0700\n"
        ).encode("ascii")

    def expect_rejected(name: str, label: str) -> None:
        try:
            load_probe_config_at(
                directory_fd,
                name,
                expected_service_uid=args.service_uid,
                expected_service_gid=args.service_gid,
            )
        except ProbeConfigRejected:
            rejected.append(label)
            return
        raise ProbeFailure(f"MA-07 accepted invalid configuration fixture: {label}")

    rejected: list[str] = []
    try:
        directory_info = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(directory_info.st_mode)
            or directory_info.st_uid != 0
            or directory_info.st_gid != 0
            or stat.S_IMODE(directory_info.st_mode) != 0o700
        ):
            raise ProbeFailure("MA-07 config fixture directory failed owner/mode validation")

        # Missing file must fail closed.
        expect_rejected("absent.conf", "absent")

        valid_bytes = base_config()
        write_fixture("valid.conf", valid_bytes)
        valid_snapshot = load_probe_config_at(
            directory_fd,
            "valid.conf",
            expected_service_uid=args.service_uid,
            expected_service_gid=args.service_gid,
        )
        if (
            valid_snapshot.service_uid != args.service_uid
            or valid_snapshot.service_gid != args.service_gid
            or valid_snapshot.client_uids != (0,)
            or not isinstance(valid_snapshot.client_uids, tuple)
        ):
            raise ProbeFailure("MA-07 valid configuration did not produce exact snapshot values")

        duplicate = valid_bytes.replace(
            f"service_uid={args.service_uid}\n".encode("ascii"),
            (
                f"service_uid={args.service_uid}\n"
                f"service_uid={args.service_uid}\n"
            ).encode("ascii"),
        )
        write_fixture("duplicate.conf", duplicate)
        expect_rejected("duplicate.conf", "duplicate-key")

        write_fixture("unknown.conf", valid_bytes + b"unexpected=1\n")
        expect_rejected("unknown.conf", "unknown-key")

        write_fixture(
            "altered.conf",
            base_config(service_uid=args.other_uid, service_gid=args.other_gid),
        )
        expect_rejected("altered.conf", "service-identity-altered")

        write_fixture("missing-key.conf", b"schema_version=1\n")
        expect_rejected("missing-key.conf", "required-key-absent")

        os.symlink("valid.conf", "symlink.conf", dir_fd=directory_fd)
        created.add("symlink.conf")
        expect_rejected("symlink.conf", "symlink")

        os.mkfifo("fifo.conf", 0o600, dir_fd=directory_fd)
        created.add("fifo.conf")
        expect_rejected("fifo.conf", "fifo")

        write_fixture("writable.conf", valid_bytes, mode=0o666)
        expect_rejected("writable.conf", "group-other-writable")

        write_fixture(
            "wrong-owner.conf",
            valid_bytes,
            uid=args.other_uid,
            gid=args.other_gid,
        )
        expect_rejected("wrong-owner.conf", "wrong-owner")

        write_fixture("oversized.conf", valid_bytes + (b"x" * 4097))
        expect_rejected("oversized.conf", "oversized")

        write_fixture("hardlink-source.conf", valid_bytes)
        os.link(
            "hardlink-source.conf",
            "hardlink.conf",
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        created.add("hardlink.conf")
        expect_rejected("hardlink.conf", "hardlink")

        ma07 = {
            "valid_configuration_accepted": True,
            "service_uid": valid_snapshot.service_uid,
            "service_gid": valid_snapshot.service_gid,
            "client_uids": list(valid_snapshot.client_uids),
            "rejected_cases": rejected,
            "rejected_count": len(rejected),
        }

        # Load once, atomically replace the pathname, and prove the existing
        # frozen snapshot remains unchanged and contains no mutable collection.
        write_fixture("snapshot.conf", valid_bytes)
        snapshot = load_probe_config_at(
            directory_fd,
            "snapshot.conf",
            expected_service_uid=args.service_uid,
            expected_service_gid=args.service_gid,
        )
        original_snapshot_values = (
            snapshot.schema_version,
            snapshot.service_uid,
            snapshot.service_gid,
            snapshot.client_uids,
            snapshot.socket_path,
            snapshot.socket_type,
            snapshot.socket_mode,
            snapshot.socket_dir_mode,
        )
        replacement_bytes = base_config(socket_path="/run/atlas/changed.sock")
        write_fixture("snapshot.next", replacement_bytes)
        os.replace(
            "snapshot.next",
            "snapshot.conf",
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        created.remove("snapshot.next")

        replacement_fd = os.open(
            "snapshot.conf",
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        try:
            replacement_data = os.read(replacement_fd, 4097)
        finally:
            os.close(replacement_fd)
        replacement_snapshot = parse_probe_config(replacement_data)

        frozen_fields = False
        try:
            setattr(snapshot, "service_uid", args.other_uid)
        except (AttributeError, TypeError):
            frozen_fields = True
        immutable_collection = False
        try:
            snapshot.client_uids[0] = args.other_uid  # type: ignore[index]
        except (TypeError, AttributeError):
            immutable_collection = True

        current_snapshot_values = (
            snapshot.schema_version,
            snapshot.service_uid,
            snapshot.service_gid,
            snapshot.client_uids,
            snapshot.socket_path,
            snapshot.socket_type,
            snapshot.socket_mode,
            snapshot.socket_dir_mode,
        )
        unchanged = current_snapshot_values == original_snapshot_values and (
            snapshot.service_uid == args.service_uid
            and snapshot.service_gid == args.service_gid
            and snapshot.socket_path == "/run/atlas/admin.sock"
        )
        if not (
            replacement_snapshot.socket_path == "/run/atlas/changed.sock"
            and unchanged
            and frozen_fields
            and immutable_collection
        ):
            raise ProbeFailure("MA-08 snapshot changed or exposed mutable configuration state")

        ma08 = {
            "loaded_socket_path": snapshot.socket_path,
            "replacement_socket_path": replacement_snapshot.socket_path,
            "snapshot_socket_path_after_replacement": snapshot.socket_path,
            "snapshot_unchanged": unchanged,
            "frozen_fields": frozen_fields,
            "immutable_collections": immutable_collection,
        }
        return ma07, ma08
    finally:
        for name in sorted(created, reverse=True):
            os.unlink(name, dir_fd=directory_fd)
        remaining = os.listdir(directory_fd)
        if remaining:
            raise ProbeFailure(
                f"MA-07/MA-08 config fixture contains unexpected entries: {remaining}"
            )
        os.close(directory_fd)
        config_dir.rmdir()



def _assert_no_protocol_response(peer: socket.socket, scenario: str) -> None:
    try:
        response = peer.recv(1, socket.MSG_DONTWAIT)
    except BlockingIOError:
        return
    except OSError as exc:
        raise ProbeFailure(
            f"{scenario}: peer socket failed while checking response "
            f"(exception={type(exc).__name__}, errno={exc.errno}, {exc.strerror})"
        ) from exc
    if response:
        raise ProbeFailure(f"{scenario}: handler emitted protocol bytes for rejected transport")


def _scenario_disconnect() -> dict:
    """Exercise real handler EOF behavior after an authorized peer closes its send side."""
    from atlas.platform_admin_ipc import (
        AdminPeerDisconnected,
        handle_admin_connection,
        read_peer_credentials,
    )

    peer, connection = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        credentials = read_peer_credentials(connection)
        if credentials.uid != 0:
            raise ProbeFailure("MA-09 fixture peer did not have kernel UID 0")
        peer.shutdown(socket.SHUT_WR)
        try:
            handle_admin_connection(
                connection,
                allowed_peer_uids=frozenset({0}),
                read_timeout_seconds=1.0,
                write_timeout_seconds=1.0,
            )
        except AdminPeerDisconnected as exc:
            if exc.code != "PEER_DISCONNECTED":
                raise ProbeFailure(f"MA-09 returned unexpected disconnect code: {exc.code}")
        else:
            raise ProbeFailure("MA-09 handler accepted a peer that sent EOF without a request")

        _assert_no_protocol_response(peer, "MA-09")
        return {
            "transport_family": "AF_UNIX",
            "socket_type": "SOCK_SEQPACKET",
            "kernel_peer_uid": credentials.uid,
            "request_bytes_sent": 0,
            "disconnect_observed": True,
            "rejection_code": "PEER_DISCONNECTED",
            "response_bytes": 0,
            "request_accepted": False,
        }
    finally:
        peer.close()
        connection.close()


def _scenario_transport() -> dict:
    """Prove the real handler rejects wrong family/type before consuming a packet."""
    from atlas.platform_admin_ipc import AdminProtocolRejected, handle_admin_connection

    request_id, packet = _request_packet()
    cases: list[dict[str, object]] = []
    sockets: list[socket.socket] = []
    listener: socket.socket | None = None
    try:
        unix_peer, unix_connection = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_STREAM
        )
        sockets.extend((unix_peer, unix_connection))
        unix_peer.sendall(packet)

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(2.0)
        tcp_peer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sockets.append(tcp_peer)
        tcp_peer.settimeout(2.0)
        tcp_peer.connect(listener.getsockname())
        # The timeout is only needed for connect. Reset Python's socket
        # timeout mode before MSG_DONTWAIT checks; otherwise Python may
        # implement recv through select() and raise socket.timeout instead
        # of the expected BlockingIOError when no response is queued.
        tcp_peer.settimeout(None)
        tcp_connection, _address = listener.accept()
        sockets.append(tcp_connection)
        tcp_peer.sendall(packet)

        for label, peer, connection, expected_family, expected_type in (
            ("unix-stream", unix_peer, unix_connection, socket.AF_UNIX, socket.SOCK_STREAM),
            ("inet-stream", tcp_peer, tcp_connection, socket.AF_INET, socket.SOCK_STREAM),
        ):
            if connection.family != expected_family:
                raise ProbeFailure(f"MA-10 {label} fixture family mismatch")
            actual_type = connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
            if actual_type != expected_type:
                raise ProbeFailure(f"MA-10 {label} fixture socket type mismatch")
            try:
                handle_admin_connection(
                    connection,
                    allowed_peer_uids=frozenset({0}),
                    read_timeout_seconds=1.0,
                    write_timeout_seconds=1.0,
                )
            except AdminProtocolRejected as exc:
                if exc.code != "INVALID_REQUEST":
                    raise ProbeFailure(
                        f"MA-10 {label} returned unexpected rejection code: {exc.code}"
                    )
            else:
                raise ProbeFailure(f"MA-10 handler accepted unsupported transport: {label}")

            # The valid request must still be queued: the handler rejected
            # family/type before reading or decoding any protocol bytes.
            queued_prefix = connection.recv(
                1, socket.MSG_PEEK | socket.MSG_DONTWAIT
            )
            if queued_prefix != packet[:1]:
                raise ProbeFailure(
                    f"MA-10 {label} consumed the first request byte before rejection"
                )
            _assert_no_protocol_response(peer, f"MA-10 {label}")
            cases.append({
                "case": label,
                "family": "AF_UNIX" if expected_family == socket.AF_UNIX else "AF_INET",
                "socket_type": "SOCK_STREAM",
                "rejection_code": "INVALID_REQUEST",
                "request_first_byte_still_queued": True,
                "response_bytes": 0,
            })

        return {
            "request_id": request_id,
            "rejected_cases": cases,
            "rejected_count": len(cases),
            "rejected_before_read": True,
        }
    finally:
        for item in reversed(sockets):
            try:
                item.close()
            except OSError:
                pass
        if listener is not None:
            listener.close()


def _cleanup_root(
    root: Path, public_root: Path, args: argparse.Namespace
) -> str:
    # Both paths are fresh root-owned directories under /run. The private
    # root is 0700; the public traversal fixture is 0711 and not writable by
    # group/others. Child servers must exit before this scoped cleanup.
    info = root.lstat()
    public_info = public_root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ProbeFailure("private sandbox root identity changed; refusing cleanup")
    if (
        not stat.S_ISDIR(public_info.st_mode)
        or public_info.st_uid != 0
        or stat.S_IMODE(public_info.st_mode) != 0o711
        or public_info.st_mode & 0o022
    ):
        raise ProbeFailure("public fixture root identity changed; refusing cleanup")
    if list(root.iterdir()):
        raise ProbeFailure("private sandbox contains unexpected entries; preserving it")
    expected_public_entries = {
        "probe-runtime", "auth-service", "wrong-server", "capacity-service"
    }
    actual_public_entries = {entry.name for entry in public_root.iterdir()}
    if not actual_public_entries.issubset(expected_public_entries):
        raise ProbeFailure("public sandbox contains unexpected entries; preserving it")
    fixture_directories = (
        ("auth-service", args.service_uid, args.service_gid, 0o711),
        ("capacity-service", args.service_uid, args.service_gid, 0o711),
        ("wrong-server", args.other_uid, args.other_gid, 0o700),
    )
    for name, expected_uid, expected_gid, expected_mode in fixture_directories:
        candidate = public_root / name
        try:
            entry = candidate.lstat()
        except FileNotFoundError:
            continue
        if (
            not stat.S_ISDIR(entry.st_mode)
            or entry.st_uid != expected_uid
            or entry.st_gid != expected_gid
            or stat.S_IMODE(entry.st_mode) != expected_mode
        ):
            raise ProbeFailure(f"fixture directory identity changed: {name}")
        if list(candidate.iterdir()):
            raise ProbeFailure(f"fixture directory {name} contains unexpected entries; preserving sandbox")
    shutil.rmtree(root)
    shutil.rmtree(public_root)
    return "private and traversal fixture /run sandboxes removed after child processes exited"


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _main_parent(args: argparse.Namespace) -> int:
    root: Path | None = None
    public_root: Path | None = None
    servers: list[Server] = []
    started = time.monotonic()
    results: list[dict[str, object]] = []
    cleanup = "not started"
    overall = "FAIL"
    try:
        root, public_root = _preflight(args)
        script = _stage_probe_runtime(public_root)
        service_dir = public_root / "capacity-service"
        _create_fixture_dir(service_dir, args.service_uid, args.service_gid, 0o711)
        service_socket = service_dir / "capacity.sock"
        server = _start_server(
            script, service_socket, args.service_uid, args.service_gid, 0o666, 0, servers
        )
        auth = _scenario_mutual_auth(public_root, args, script, servers)
        results.append({"id": "MA-01,MA-02,MA-03,MA-04,MA-05,MA-06", "status": "PASS", "observations": auth})
        ma07, ma08 = _scenario_configuration(root, args)
        results.append({"id": "MA-07", "status": "PASS", "observations": ma07})
        results.append({"id": "MA-08", "status": "PASS", "observations": ma08})
        disconnect = _scenario_disconnect()
        results.append({"id": "MA-09", "status": "PASS", "observations": disconnect})
        transport = _scenario_transport()
        results.append({"id": "MA-10", "status": "PASS", "observations": transport})
        capacity = _scenario_capacity(server, service_socket)
        results.append({"id": "CP-01,CP-04", "status": "PASS", "observations": capacity})
        backlog = _scenario_backlog(server, service_socket)
        results.append({"id": "CP-02,CP-03", "status": "PASS", "observations": backlog})
        results.append({
            "id": "CP-05..CP-12",
            "status": "INCOMPLETE",
            "detail": "read/write/global deadline adversaries, exception recovery, payload/depth boundaries and full FD accounting remain unimplemented",
        })
        overall = "INCOMPLETE"
    except ProbeIncomplete as exc:
        results.append({"id": "PREFLIGHT", "status": "INCOMPLETE", "detail": str(exc)})
        overall = "INCOMPLETE"
    except Exception as exc:
        results.append({"id": "PROBE", "status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"})
        overall = "FAIL"
    finally:
        stop_errors: list[str] = []
        for server in reversed(servers):
            try:
                server.stop()
            except Exception as exc:
                stop_errors.append(str(exc))
        if root is not None and public_root is not None and not stop_errors:
            try:
                cleanup = _cleanup_root(root, public_root, args)
            except Exception as exc:
                stop_errors.append(str(exc))
        elif root is not None or public_root is not None:
            cleanup = "sandbox preserved because a child server did not stop cleanly"
        if stop_errors:
            results.append({"id": "CLEANUP", "status": "FAIL", "detail": "; ".join(stop_errors)})
            overall = "FAIL"
        elif cleanup == "not started":
            pass
    report = {
        "probe": "A-IPC-02-mutual-auth-capacity",
        "overall": overall,
        "commit": _git_commit(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "effective_uid": os.geteuid(),
        "fixture_service_uid": args.service_uid,
        "fixture_service_gid": args.service_gid,
        "fixture_other_uid": args.other_uid,
        "fixture_other_gid": args.other_gid,
        "limits": {
            "workers": WORKERS,
            "backlog": BACKLOG,
            "read_timeout_seconds": READ_TIMEOUT,
            "write_timeout_seconds": WRITE_TIMEOUT,
            "global_deadline_seconds": GLOBAL_DEADLINE,
            "request_bytes": REQUEST_LIMIT,
            "response_bytes": RESPONSE_LIMIT,
            "rlimit_nofile": FD_LIMIT,
        },
        "duration_seconds": round(time.monotonic() - started, 3),
        "cleanup": cleanup,
        "scenarios": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if overall == "PASS" else (1 if overall == "FAIL" else 2)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-uid", type=int)
    parser.add_argument("--service-gid", type=int)
    parser.add_argument("--other-uid", type=int)
    parser.add_argument("--other-gid", type=int)
    parser.add_argument("--confirm-disposable-vm", action="store_true")
    parser.add_argument("--confirm-fixture-ids", action="store_true")
    parser.add_argument("--server-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--client-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--negative-client-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--socket", help=argparse.SUPPRESS)
    parser.add_argument("--socket-mode", type=lambda value: int(value, 0), default=0o600, help=argparse.SUPPRESS)
    parser.add_argument("--allowed-uid", type=int, default=0, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.server_child:
        if not args.socket:
            return 3
        return _server_child(args.socket, args.socket_mode, args.allowed_uid)
    if args.client_child:
        if not args.socket:
            return 3
        return _client_child(args.socket)
    if args.negative_client_child:
        if not args.socket:
            return 3
        return _negative_euid_client_child(args.socket)
    required = (args.service_uid, args.service_gid, args.other_uid, args.other_gid)
    if any(value is None for value in required):
        print(json.dumps({
            "probe": "A-IPC-02-mutual-auth-capacity",
            "overall": "INCOMPLETE",
            "reason": "explicit --service-uid/--service-gid/--other-uid/--other-gid are required",
        }, indent=2))
        return 2
    return _main_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
