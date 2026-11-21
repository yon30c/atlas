#!/usr/bin/env python3
"""Root-only, disposable-VM probe for mutual SO_PEERCRED auth and bounded IPC.

This is an isolated experiment. It does not install services, touch SQLite,
modify host accounts, or create a persistent Atlas listener.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import platform
import resource
import select
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


class ProbeIncomplete(Exception):
    pass


class ProbeFailure(Exception):
    pass


def emit(**event: object) -> None:
    print(json.dumps(event, sort_keys=True), flush=True)


def _drop_identity(uid: int, gid: int):
    """Return a pre-exec hook that drops only the child process credentials."""
    def apply() -> None:
        os.setgroups([])
        os.setresgid(gid, gid, gid)
        os.setresuid(uid, uid, uid)
    return apply


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


def _serve_authenticated(connection: socket.socket, allowed_uid: int) -> None:
    """Fixture handler: authenticate before recv and enforce one global deadline."""
    from atlas.platform_admin_ipc import (
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

    deadline = time.monotonic() + GLOBAL_DEADLINE
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

    request = decode_admin_request(packet)
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
        )

        def worker(connection: socket.socket) -> None:
            nonlocal active, max_active, max_workers
            with lock:
                active += 1
                max_active = max(max_active, active)
                max_workers = max(max_workers, active)
                emit(event="metrics", active=active, max_active=max_active,
                     max_workers=max_workers, accepted=accepted)
            try:
                with connection:
                    _serve_authenticated(connection, allowed_uid)
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
                pool.submit(worker, connection)
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


class Server:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.events: list[dict[str, object]] = []

    def next_event(self, timeout: float = 3.0) -> dict[str, object]:
        if self.process.stdout is None:
            raise ProbeFailure("server stdout is unavailable")
        ready, _write, _error = select.select([self.process.stdout], [], [], timeout)
        if not ready:
            raise ProbeFailure("timed out waiting for server evidence")
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise ProbeFailure(f"server exited unexpectedly: {stderr}")
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProbeFailure(f"server emitted invalid JSON: {line!r}") from exc
        self.events.append(event)
        if event.get("event") in {"startup_error", "server_error", "worker_error", "cleanup_error"}:
            raise ProbeFailure(f"server reported {event}")
        return event

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
        if self.process.returncode != 0:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise ProbeFailure(f"server exited {self.process.returncode}: {stderr}")


def _start_server(script: Path, socket_path: Path, uid: int, gid: int,
                  socket_mode: int, allowed_uid: int) -> Server:
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
        preexec_fn=_drop_identity(uid, gid),
    )
    server = Server(process)
    try:
        ready = server.wait_event("ready", timeout=5.0)
        if ready.get("uid") != uid or ready.get("gid") != gid:
            raise ProbeFailure("server child did not retain the requested fixture identity")
        if ready.get("rlimit_nofile") != FD_LIMIT:
            raise ProbeFailure("server RLIMIT_NOFILE is not exactly 64")
        return server
    except Exception:
        try:
            server.stop()
        except Exception:
            pass
        raise


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


def _preflight(args: argparse.Namespace) -> Path:
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
    run_dir = Path("/run")
    info = run_dir.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise ProbeIncomplete("/run must be a real root-owned directory not writable by group/others")
    tempfile = __import__("tempfile")
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
    root: Path, public_root: Path, args: argparse.Namespace, script: Path
) -> dict:
    service_dir = public_root / "auth-service"
    wrong_server_dir = public_root / "wrong-server"
    _create_fixture_dir(service_dir, args.service_uid, args.service_gid, 0o711)
    _create_fixture_dir(wrong_server_dir, args.other_uid, args.other_gid, 0o700)
    service_socket = service_dir / "admin.sock"
    wrong_socket = wrong_server_dir / "admin.sock"

    server = _start_server(
        script, service_socket, args.service_uid, args.service_gid, 0o666, 0
    )
    try:
        peer, response = _connect_as_root(service_socket, args.service_uid, send_request=True)
        if peer.uid != args.service_uid or response is None:
            raise ProbeFailure("valid root client did not authenticate the service")
        valid = {"server_uid": peer.uid, "request_id": response["request_id"]}

        wrong_server = _start_server(
            script, wrong_socket, args.other_uid, args.other_gid, 0o600, 0
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
            preexec_fn=_drop_identity(args.other_uid, args.other_gid),
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
            "valid_root_client": valid,
            "wrong_server_rejected_before_send": rejected_server,
            "wrong_client_rejected_before_recv": {
                "peer_uid": args.other_uid,
                "response_bytes": 0,
            },
        }
    finally:
        server.stop()


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
        time.sleep(0.25)
        observed_max = int(first.get("max_active", 0))
        if observed_max > WORKERS:
            raise ProbeFailure("active workers exceeded the configured fixed pool")
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


def _cleanup_root(root: Path, public_root: Path) -> str:
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
    shutil.rmtree(root)
    shutil.rmtree(public_root)
    return "private and traversal fixture /run sandboxes removed after child processes exited"


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
            script, service_socket, args.service_uid, args.service_gid, 0o666, 0
        )
        servers.append(server)
        auth = _scenario_mutual_auth(root, public_root, args, script)
        results.append({"id": "MA-01,MA-02,MA-04,MA-05", "status": "PASS", "observations": auth})
        capacity = _scenario_capacity(server, service_socket)
        results.append({"id": "CP-01,CP-04", "status": "PASS", "observations": capacity})
        results.append({
            "id": "MA-03,MA-06..MA-10,CP-02..CP-03,CP-05..CP-12",
            "status": "INCOMPLETE",
            "detail": "EUID-negative pre-connect, forged identity fields, config immutability, disconnect/transport variants, exact backlog saturation, read/write/global deadline adversaries, exception recovery, payload/depth boundaries and full FD accounting remain unimplemented",
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
                cleanup = _cleanup_root(root, public_root)
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
        "commit": None,
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
