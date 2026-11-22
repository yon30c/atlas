#!/usr/bin/env python3
"""A-IPC-05 listener-quiescence probe (disposable Atlas-VM-test only).

This runner is deliberately fail-closed. It never operates on a pre-existing
unit, never installs persistent systemd configuration, and never performs
stale-path recovery. Scenarios without a complete executable oracle remain
INCOMPLETE; they are never represented as PASS.
"""
from __future__ import annotations

import argparse
import ctypes.util
import errno
import fcntl
import grp
import json
import os
from pathlib import Path
import platform
import pwd
import secrets
import selectors
import signal
import socket
import stat
import subprocess
import sys
import time
import uuid

SCHEMA = "atlas.listener-quiescence-probe/1"
PROBE_VERSION = "0.1.0"
EXPECTED = tuple(f"QP-{number:02d}" for number in range(1, 16))
MAX_REPORT = 1024 * 1024
MAX_SCENARIO = 32 * 1024
MAX_DBUS = 16 * 1024
MAX_CGROUP = 4096
BASE = Path("/run/atlas-qp")
BUS = "org.freedesktop.systemd1"
MANAGER = "/org/freedesktop/systemd1"
MANAGER_IFACE = "org.freedesktop.systemd1.Manager"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
UNIT_IFACE = "org.freedesktop.systemd1.Unit"
SERVICE_IFACE = "org.freedesktop.systemd1.Service"
RESOURCE_IFACE = "org.freedesktop.systemd1.ResourceControl"
SERVICE_UID = 2005
SERVICE_GID = 2005
OTHER_UID = 2006
OTHER_GID = 2006
STOP_TIMEOUT = 8.0


class ProbeError(RuntimeError):
    pass


class Incomplete(ProbeError):
    pass


def mono() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def emit(event: dict) -> None:
    print(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)


def bounded_run(argv: list[str], timeout: float = 5.0, limit: int = MAX_DBUS) -> bytes:
    """Run a fixed argv with streaming output bounds and process-group timeout."""
    if not argv or timeout <= 0 or limit < 1:
        raise Incomplete("invalid bounded subprocess request")
    process = subprocess.Popen(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True, close_fds=True,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
    )
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    streams = ((process.stdout, "stdout"), (process.stderr, "stderr"))
    try:
        for stream, label in streams:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        deadline = time.monotonic() + timeout
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Incomplete(f"{argv[0]} exceeded {timeout:.1f}s timeout")
            for key, _mask in selector.select(min(remaining, 0.1)):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                target = buffers[key.data]
                target.extend(chunk)
                if len(target) > limit:
                    raise Incomplete(
                        f"{argv[0]} {key.data} exceeded {limit}-byte output limit"
                    )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Incomplete(f"{argv[0]} exceeded {timeout:.1f}s timeout")
        returncode = process.wait(timeout=remaining)
    except (OSError, subprocess.TimeoutExpired) as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise Incomplete(f"{argv[0]} subprocess supervision failed: {type(exc).__name__}") from exc
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    finally:
        selector.close()
        for stream, _label in streams:
            if not stream.closed:
                stream.close()
    if returncode:
        raise Incomplete(
            f"{argv[0]} exited {returncode}; "
            f"stderr={bytes(buffers['stderr'][:512]).decode('utf-8', 'replace')}"
        )
    return bytes(buffers["stdout"])


def busctl_json(*args: str, timeout: float = 5.0) -> dict:
    raw = bounded_run(
        ["busctl", "--system", "--json=short", *args], timeout=timeout
    )
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Incomplete("busctl returned invalid JSON") from exc
    if not isinstance(value, dict) or "type" not in value or "data" not in value:
        raise Incomplete("busctl JSON lacks typed type/data fields")
    return value


def dbus_property(path: str, interface: str, name: str, expected_type: str):
    result = busctl_json(
        "get-property", BUS, path, interface, name
    )
    if result["type"] != expected_type:
        raise Incomplete(
            f"D-Bus property {interface}.{name} has type "
            f"{result['type']!r}, expected {expected_type!r}"
        )
    return result["data"]


def unit_path(name: str) -> str:
    result = busctl_json(
        "call", BUS, MANAGER, MANAGER_IFACE, "GetUnit", "s", name
    )
    if result["type"] != "o" or not isinstance(result["data"], str):
        raise Incomplete("GetUnit did not return one object path")
    if not result["data"].startswith("/org/freedesktop/systemd1/unit/"):
        raise Incomplete("GetUnit returned an unexpected object path")
    return result["data"]


def list_jobs_for_unit(name: str) -> list[dict]:
    result = busctl_json("call", BUS, MANAGER, MANAGER_IFACE, "ListJobs")
    if result["type"] != "a(usssoo)" or not isinstance(result["data"], list):
        raise Incomplete("Manager.ListJobs returned an unexpected signature or shape")
    matches = []
    for row in result["data"]:
        if (
            not isinstance(row, list) or len(row) != 6
            or not isinstance(row[0], int)
            or not all(isinstance(row[index], str) for index in range(1, 6))
        ):
            raise Incomplete("Manager.ListJobs contains a malformed typed row")
        if row[1] == name:
            matches.append({
                "id": row[0], "unit": row[1], "type": row[2],
                "state": row[3], "unit_path": row[4], "job_path": row[5],
            })
    return matches


def assert_unit_absent(name: str) -> None:
    result = busctl_json(
        "call", BUS, MANAGER, MANAGER_IFACE, "ListUnitsByNames", "as", "1", name
    )
    if result["type"] != "a(ssssssouso)" or not isinstance(result["data"], list):
        raise Incomplete("ListUnitsByNames returned an unexpected signature or shape")
    if result["data"]:
        raise Incomplete(f"random fixture unit name already exists: {name}")


def git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[3],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=2.0, check=False,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
    )
    if result.returncode or len(result.stdout) > 128:
        raise Incomplete("cannot identify the exact checkout commit")
    value = result.stdout.decode("ascii", "strict").strip()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise Incomplete("git rev-parse returned an invalid commit identifier")
    return value


def unit_snapshot(name: str) -> dict:
    path = unit_path(name)
    values = {
        "Id": dbus_property(path, UNIT_IFACE, "Id", "s"),
        "LoadState": dbus_property(path, UNIT_IFACE, "LoadState", "s"),
        "ActiveState": dbus_property(path, UNIT_IFACE, "ActiveState", "s"),
        "SubState": dbus_property(path, UNIT_IFACE, "SubState", "s"),
        "InvocationID": dbus_property(path, UNIT_IFACE, "InvocationID", "ay"),
        "ControlGroup": dbus_property(path, SERVICE_IFACE, "ControlGroup", "s"),
        "KillMode": dbus_property(path, SERVICE_IFACE, "KillMode", "s"),
        "Restart": dbus_property(path, SERVICE_IFACE, "Restart", "s"),
        "Delegate": dbus_property(path, RESOURCE_IFACE, "Delegate", "b"),
        "Transient": dbus_property(path, UNIT_IFACE, "Transient", "b"),
        "Job": dbus_property(path, UNIT_IFACE, "Job", "(uo)"),
        "Triggers": dbus_property(path, UNIT_IFACE, "Triggers", "as"),
        "TriggeredBy": dbus_property(path, UNIT_IFACE, "TriggeredBy", "as"),
    }
    if values["Id"] != name or values["LoadState"] != "loaded":
        raise Incomplete("systemd returned a different or unloaded unit")
    if values["KillMode"] != "control-group" or values["Restart"] != "no":
        raise Incomplete("fixture unit lifecycle properties differ from contract")
    if not values["Transient"]:
        raise Incomplete("fixture unit is not transient")
    if values["Triggers"] or values["TriggeredBy"]:
        raise Incomplete("fixture unit unexpectedly has activation relationships")
    if not isinstance(values["InvocationID"], list) or len(values["InvocationID"]) != 16:
        raise Incomplete("InvocationID is not a 16-byte D-Bus ay")
    if not isinstance(values["Job"], list) or len(values["Job"]) != 2:
        raise Incomplete("Unit.Job has an unexpected D-Bus representation")
    jobs = list_jobs_for_unit(name)
    job_id, job_path = values["Job"]
    if job_id == 0:
        if job_path != "/" or jobs:
            raise Incomplete("Unit.Job and Manager.ListJobs disagree about no pending job")
    else:
        if len(jobs) != 1 or jobs[0]["id"] != job_id or jobs[0]["job_path"] != job_path:
            raise Incomplete("Unit.Job and Manager.ListJobs disagree about pending job")
    values["ListJobs"] = jobs
    return values


def cgroup_mount() -> tuple[Path, Path]:
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="ascii").splitlines()
    except OSError as exc:
        raise Incomplete("cannot read mountinfo") from exc
    found = []
    for line in lines:
        fields = line.split()
        if "-" not in fields:
            continue
        sep = fields.index("-")
        if len(fields) > sep + 1 and fields[sep + 1] == "cgroup2":
            found.append((Path(fields[3]), Path(fields[4])))
    if len(found) != 1:
        raise Incomplete("cgroup v2 mount is not unique")
    return found[0]


def cgroup_events(mount_root: Path, control_group: str) -> dict:
    if not control_group.startswith("/") or ".." in Path(control_group).parts:
        raise Incomplete("systemd returned an unsafe ControlGroup path")
    path = mount_root / control_group.lstrip("/") / "cgroup.events"
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            chunks = []
            total = 0
            while True:
                chunk = os.read(fd, min(1024, MAX_CGROUP + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_CGROUP:
                    raise Incomplete("cgroup.events exceeds 4096 bytes")
            raw = b"".join(chunks)
        finally:
            os.close(fd)
    except OSError as exc:
        raise Incomplete(f"cannot read cgroup.events: errno={exc.errno}") from exc
    try:
        text = raw.decode("ascii", "strict")
    except UnicodeError as exc:
        raise Incomplete("cgroup.events is not ASCII") from exc
    parsed = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[0] in parsed or fields[0] not in {"populated", "frozen"}:
            raise Incomplete("cgroup.events contains malformed, duplicate or unknown keys")
        if fields[1] not in {"0", "1"}:
            raise Incomplete("cgroup.events contains a non-boolean value")
        parsed[fields[0]] = int(fields[1])
    if "populated" not in parsed:
        raise Incomplete("cgroup.events lacks populated")
    return {"path": str(path), "raw": text, "values": parsed}


class _TestLifecycleSupervisor:
    """Harness-only lifecycle gate; never imported by the Atlas runtime."""

    def __init__(self, lock_fd: int, marker: Path, run_id: str, *, allow_owner: bool = True):
        self.lock_fd = lock_fd
        self.marker = marker
        self.run_id = run_id
        self.allow_owner = allow_owner
        self.active = True

    def request(self, action: str, argv: list[str], *, actor_run_id: str) -> bytes:
        if not self.active:
            raise Incomplete("test lifecycle supervisor is unavailable")
        if action not in {"start", "stop", "restart"}:
            raise Incomplete("test lifecycle supervisor received an unsupported action")
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            marker_data = json.loads(self.marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Incomplete("test lifecycle supervisor cannot verify its gate") from exc
        if marker_data.get("schema") != SCHEMA or marker_data.get("run_id") != self.run_id:
            raise Incomplete("test lifecycle supervisor marker ownership mismatch")
        if not self.allow_owner:
            raise Incomplete("sticky maintenance marker blocks lifecycle until explicit manual recovery")
        if actor_run_id != self.run_id:
            raise PermissionError("second authorized actor rejected by maintenance gate")
        if not argv or argv[0] not in {"systemd-run", "systemctl"}:
            raise Incomplete("test lifecycle supervisor accepts only fixed systemd clients")
        return bounded_run(argv, timeout=8.0)

    def crash(self) -> None:
        self.active = False


_ACTIVE_SUPERVISOR: _TestLifecycleSupervisor | None = None
_ACTIVE_RUN_ID: str | None = None


def systemd_stop(name: str) -> None:
    # Lifecycle requests pass through the harness-only supervisor. D-Bus/cgroup
    # observations, not command output, determine the resulting state.
    if _ACTIVE_SUPERVISOR is None or _ACTIVE_RUN_ID is None:
        raise Incomplete("no active test lifecycle supervisor")
    _ACTIVE_SUPERVISOR.request(
        "stop", ["systemctl", "--no-block", "stop", name],
        actor_run_id=_ACTIVE_RUN_ID,
    )


def wait_inactive(name: str, deadline: float) -> dict:
    last = None
    while time.monotonic() < deadline:
        last = unit_snapshot(name)
        if last["ActiveState"] == "inactive" and last["Job"][0] == 0:
            return last
        time.sleep(0.05)
    raise Incomplete(
        f"unit did not become inactive before deadline; "
        f"state={last['ActiveState'] if last else 'unavailable'}"
    )


def fixture_main(args: argparse.Namespace) -> int:
    """Unprivileged systemd service fixture; never used against Atlas."""
    listener = None
    child = None
    try:
        if args.hold_child:
            child = os.fork()
            if child == 0:
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                while True:
                    signal.pause()
        if args.ignore_term:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        ready = {"pid": os.getpid(), "fd": None}
        if not args.no_listener:
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            listener.set_inheritable(False)
            os.umask(0o177)
            listener.bind(args.socket)
            listener.listen(1)
            info = os.stat(args.socket, follow_symlinks=False)
            ready.update({
                "fd": listener.fileno(), "device": info.st_dev, "inode": info.st_ino,
                "uid": info.st_uid, "gid": info.st_gid,
                "mode": stat.S_IMODE(info.st_mode),
                "socket_type": listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE),
                "accepting": listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN),
                "cloexec": not os.get_inheritable(listener.fileno()),
            })
        fd = os.open(
            args.ready, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC,
            0o600,
        )
        try:
            os.write(fd, json.dumps(ready, sort_keys=True).encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)
        while True:
            signal.pause()
    except BaseException as exc:
        print(f"fixture failure: {type(exc).__name__}", file=sys.stderr)
        return 3
    finally:
        if listener is not None:
            listener.close()
        if child is not None:
            try:
                os.waitpid(child, os.WNOHANG)
            except ChildProcessError:
                pass
    return 0


def preflight() -> dict:
    if not sys.platform.startswith("linux") or os.geteuid() != 0:
        raise Incomplete("direct EUID 0 on Linux is required")
    if platform.python_version() != "3.13.5":
        raise Incomplete("Python profile mismatch; expected 3.13.5")
    if platform.release() != "6.12.117+deb13-amd64":
        raise Incomplete("kernel profile mismatch; expected 6.12.117+deb13-amd64")
    try:
        debian = Path("/etc/debian_version").read_text(encoding="ascii").strip()
    except OSError as exc:
        raise Incomplete("cannot identify Debian release") from exc
    if not debian.startswith("13"):
        raise Incomplete("Debian 13 is required")
    for executable in ("busctl", "systemd-run", "systemctl", "git"):
        if not __import__("shutil").which(executable):
            raise Incomplete(f"required executable missing: {executable}")
    if not ctypes.util.find_library("seccomp"):
        raise Incomplete("libseccomp.so.2 is unavailable")
    for uid, gid, label in (
        (SERVICE_UID, SERVICE_GID, "SERVICE"),
        (OTHER_UID, OTHER_GID, "OTHER"),
    ):
        try:
            account = pwd.getpwuid(uid)
            group = grp.getgrgid(gid)
        except KeyError as exc:
            raise Incomplete(f"{label} fixture UID/GID is not provisioned") from exc
        if account.pw_gid != gid:
            raise Incomplete(f"{label} account primary GID differs from fixture GID")
        if uid == 0 or gid == 0:
            raise Incomplete("fixture identities must be non-root")
    bus_version = bounded_run(["busctl", "--version"], timeout=3.0, limit=4096)
    if b"systemd 257" not in bus_version:
        raise Incomplete("systemd/busctl version is outside the 257 profile")
    root, mount = cgroup_mount()
    if root != Path("/"):
        raise Incomplete("cgroup v2 mount does not expose the unified hierarchy root")
    if not (mount / "cgroup.controllers").is_file():
        raise Incomplete("cgroup v2 unified hierarchy is unavailable")
    run_stat = os.stat("/run", follow_symlinks=False)
    if not stat.S_ISDIR(run_stat.st_mode) or run_stat.st_uid != 0 or run_stat.st_gid != 0:
        raise Incomplete("/run is not a root:root directory")
    run_mounts = []
    for line in Path("/proc/self/mountinfo").read_text(encoding="ascii").splitlines():
        fields = line.split()
        if len(fields) > 5 and fields[4] == "/run" and "-" in fields:
            sep = fields.index("-")
            run_mounts.append(fields[sep + 1])
    if run_mounts != ["tmpfs"]:
        raise Incomplete("/run is not a unique tmpfs mount")
    # A harmless read-only D-Bus query proves the system manager is reachable.
    busctl_json("get-property", BUS, MANAGER, "org.freedesktop.systemd1.Manager", "Version")
    checkout_commit = git_commit()
    return {
        "git_commit": checkout_commit,
        "debian": debian, "kernel": platform.release(),
        "python": platform.python_version(), "busctl": bus_version.decode("utf-8", "replace").strip(),
        "cgroup2_root": str(root), "cgroup2_mount": str(mount),
        "service_uid_gid": [SERVICE_UID, SERVICE_GID],
        "other_uid_gid": [OTHER_UID, OTHER_GID],
        "effective_uid": os.geteuid(),
        "mutating_preflight": False,
    }


def _safe_json_file(path: Path, value: dict, limit: int) -> None:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(raw) > limit:
        raise Incomplete(f"JSON evidence exceeds {limit} bytes")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise Incomplete("new JSON evidence file identity/mode is invalid")
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(errno.EIO, "short evidence write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _rewrite_json_file(path: Path, value: dict, limit: int) -> None:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(raw) > limit:
        raise Incomplete(f"JSON evidence exceeds {limit} bytes")
    fd = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise Incomplete("report file identity/mode changed before final rewrite")
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(errno.EIO, "short report rewrite")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def update_gate_marker(marker: Path, run_id: str, name: str, snapshot: dict, phase: str) -> None:
    _rewrite_json_file(marker, {
        "schema": SCHEMA, "run_id": run_id, "unit": name,
        "invocation_id": snapshot["InvocationID"], "phase": phase,
    }, 4096)


def _start_fixture(name: str, run_dir: Path, *, hold_child=False, ignore_term=False, delegate=False, no_listener=False) -> tuple[dict, Path | None, Path]:
    assert_unit_absent(name)
    socket_path = run_dir / f"{name}.sock"
    ready_path = run_dir / f"{name}.ready"
    properties = [
        "--property=Type=exec", "--property=KillMode=control-group",
        "--property=Restart=no", f"--property=Delegate={'yes' if delegate else 'no'}",
        "--property=TimeoutStopSec=6s", f"--uid={SERVICE_UID}", f"--gid={SERVICE_GID}",
    ]
    command = [
        "systemd-run", "--system", "--no-block", f"--unit={name}",
        *properties, sys.executable, "-I", str(Path(__file__).resolve()),
        "--fixture", "--socket", str(socket_path), "--ready", str(ready_path),
    ]
    if hold_child:
        command.append("--hold-child")
    if ignore_term:
        command.append("--ignore-term")
    if no_listener:
        command.append("--no-listener")
    if _ACTIVE_SUPERVISOR is None or _ACTIVE_RUN_ID is None:
        raise Incomplete("no active test lifecycle supervisor")
    _ACTIVE_SUPERVISOR.request("start", command, actor_run_id=_ACTIVE_RUN_ID)
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        try:
            ready = json.loads(ready_path.read_text(encoding="ascii"))
            break
        except FileNotFoundError:
            time.sleep(0.05)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise Incomplete("fixture readiness record is malformed") from exc
    else:
        raise Incomplete("fixture did not publish readiness")
    snap = unit_snapshot(name)
    if snap["Delegate"] != delegate:
        raise Incomplete("systemd Delegate property differs from requested fixture")
    if snap["ControlGroup"] == "":
        raise Incomplete("systemd returned an empty ControlGroup")
    if no_listener:
        if ready.get("fd") is not None:
            raise Incomplete("control-only fixture unexpectedly reported a listener FD")
        return snap, None, ready_path
    info = os.stat(socket_path, follow_symlinks=False)
    if (
        not stat.S_ISSOCK(info.st_mode) or info.st_uid != SERVICE_UID
        or info.st_gid != SERVICE_GID or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_dev != ready["device"] or info.st_ino != ready["inode"]
    ):
        raise Incomplete("fixture endpoint identity/mode differs from readiness record")
    return snap, socket_path, ready_path


def _stop_and_cleanup(name: str, initial: dict, socket_path: Path | None, ready_path: Path | None,
                      run_dir_fd: int, report: dict, *, already_stopped: bool = False,
                      cgroup_empty_confirmed: bool = False) -> dict:
    cleanup = {"unit": name, "stop_requested": False, "unit_inactive": already_stopped,
               "cgroup_empty": cgroup_empty_confirmed, "endpoint_removed": False}
    try:
        if not already_stopped:
            current = unit_snapshot(name)
            if current["InvocationID"] != initial["InvocationID"]:
                raise Incomplete("InvocationID changed before cleanup; refusing to stop replacement")
            systemd_stop(name)
            cleanup["stop_requested"] = True
            final = wait_inactive(name, time.monotonic() + STOP_TIMEOUT + 3)
            cleanup["unit_inactive"] = final["ActiveState"] == "inactive"
        if not cleanup["unit_inactive"]:
            raise Incomplete("fixture unit is not confirmed inactive")
        if not cgroup_empty_confirmed:
            _root, mount = cgroup_mount()
            events = cgroup_events(mount, initial["ControlGroup"])
            cleanup["cgroup_empty"] = events["values"]["populated"] == 0
        if not cleanup["cgroup_empty"]:
            raise Incomplete("fixture cgroup remains populated during cleanup")
        if socket_path is not None:
            name_only = socket_path.name
            current_info = os.stat(name_only, dir_fd=run_dir_fd, follow_symlinks=False)
            if (
                not stat.S_ISSOCK(current_info.st_mode)
                or current_info.st_uid != SERVICE_UID
                or current_info.st_gid != SERVICE_GID
                or stat.S_IMODE(current_info.st_mode) != 0o600
            ):
                raise Incomplete("fixture endpoint type/owner/mode is not eligible for cleanup")
            if ready_path is not None:
                ready = json.loads(ready_path.read_text(encoding="ascii"))
                if (
                    (current_info.st_dev, current_info.st_ino) != (ready["device"], ready["inode"])
                    or current_info.st_uid != ready["uid"]
                    or current_info.st_gid != ready["gid"]
                    or stat.S_IMODE(current_info.st_mode) != ready["mode"]
                ):
                    raise Incomplete("fixture endpoint identity changed; preserving it")
            os.unlink(name_only, dir_fd=run_dir_fd)
            cleanup["endpoint_removed"] = True
        if ready_path is not None:
            try:
                os.unlink(ready_path.name, dir_fd=run_dir_fd)
            except FileNotFoundError:
                pass
    except Exception as exc:
        cleanup["error"] = f"{type(exc).__name__}: {exc}"
        report["cleanup"]["safe_to_release_gate"] = False
    return cleanup



def _wait_for_deactivation(name: str, mount: Path, control_group: str, deadline: float) -> tuple[dict, dict]:
    last_unit = None
    last_events = None
    while time.monotonic() < deadline:
        last_unit = unit_snapshot(name)
        last_events = cgroup_events(mount, control_group)
        if last_unit["ActiveState"] in {"deactivating", "activating", "reloading"} and last_events["values"]["populated"] == 1:
            return last_unit, last_events
        time.sleep(0.03)
    raise Incomplete("did not observe a pending lifecycle transition with populated=1")


def run_probe(args: argparse.Namespace) -> dict:
    started_ns = mono()
    run_id = str(uuid.uuid4())
    report = {
        "schema": SCHEMA, "run_id": run_id, "probe_version": PROBE_VERSION,
        "git_commit": "unavailable", "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "started_monotonic_ns": started_ns, "preflight": {}, "gate": {},
        "unit_identity": {}, "snapshots": [], "scenarios": [],
        "cleanup": {"safe_to_release_gate": True, "resources": []},
        "recovery_pathname_mutation_performed": False,
        "systemd_socket_activation_tested": False,
    }
    try:
        report["preflight"] = preflight()
        report["git_commit"] = report["preflight"]["git_commit"]
    except Exception as exc:
        report["preflight"] = {"status": "INCOMPLETE", "reason": f"{type(exc).__name__}: {exc}"}
        report["overall"] = "INCOMPLETE"
        return report

    base_created = False
    run_dir = None
    run_dir_fd = None
    lock_fd = None
    marker = None
    marker_created = False
    try:
        try:
            os.mkdir(BASE, 0o711)
            base_created = True
            os.chown(BASE, 0, 0)
            os.chmod(BASE, 0o711)
            base_info = os.stat(BASE, follow_symlinks=False)
            if not stat.S_ISDIR(base_info.st_mode) or base_info.st_uid != 0 or base_info.st_gid != 0 or stat.S_IMODE(base_info.st_mode) != 0o711:
                raise Incomplete("new /run/atlas-qp directory identity/mode is invalid")
        except FileExistsError:
            info = os.stat(BASE, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o711:
                raise Incomplete("/run/atlas-qp exists with unexpected identity or mode")
        run_dir = BASE / run_id
        os.mkdir(run_dir, 0o730)
        os.chown(run_dir, 0, SERVICE_GID)
        os.chmod(run_dir, 0o730)
        run_dir_fd = os.open(run_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        run_dir_info = os.fstat(run_dir_fd)
        report["sandbox"] = {
            "path": str(run_dir), "device": run_dir_info.st_dev,
            "inode": run_dir_info.st_ino, "uid": run_dir_info.st_uid,
            "gid": run_dir_info.st_gid, "mode": oct(stat.S_IMODE(run_dir_info.st_mode)),
        }
        lock_path = BASE / "maintenance.lock"
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        lock_info = os.fstat(lock_fd)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != 0 or lock_info.st_gid != 0 or lock_info.st_nlink != 1 or stat.S_IMODE(lock_info.st_mode) != 0o600:
            raise Incomplete("maintenance lock identity/mode is invalid")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Incomplete("another maintenance actor owns the lock") from exc
        marker = BASE / "maintenance.marker"
        marker_data = {"schema": SCHEMA, "run_id": run_id, "phase": "preparing"}
        _safe_json_file(marker, marker_data, 4096)
        marker_created = True
        global _ACTIVE_SUPERVISOR, _ACTIVE_RUN_ID
        _ACTIVE_RUN_ID = run_id
        _ACTIVE_SUPERVISOR = _TestLifecycleSupervisor(lock_fd, marker, run_id)
        report["gate"] = {"flock_acquired": True, "sticky_marker_created": True,
                          "root_direct_bypass_protection": False,
                          "lifecycle_requests_routed_through_test_supervisor": True}
        mount_root, mount = cgroup_mount()

        # QP-01: normal service-owned listener, full stop, two empty snapshots.
        name = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial, endpoint, ready_path = _start_fixture(name, run_dir)
        report["unit_identity"][name] = initial
        update_gate_marker(marker, run_id, name, initial, "unit-started")
        before = cgroup_events(mount, initial["ControlGroup"])
        report["snapshots"].append({"scenario": "QP-01", "phase": "before-stop",
                                    "monotonic_ns": mono(), "unit": initial, "cgroup": before})
        systemd_stop(name)
        stopped = wait_inactive(name, time.monotonic() + STOP_TIMEOUT + 3)
        after1 = cgroup_events(mount, initial["ControlGroup"])
        after2 = cgroup_events(mount, initial["ControlGroup"])
        stable = unit_snapshot(name)
        quiescent = (
            stopped["ActiveState"] == "inactive" and stopped["Job"][0] == 0
            and after1["values"]["populated"] == 0 and after2["values"]["populated"] == 0
            and stable["InvocationID"] == initial["InvocationID"]
            and stable["ControlGroup"] == initial["ControlGroup"]
            and stable["ActiveState"] == "inactive" and stable["Job"][0] == 0
        )
        report["snapshots"].append({"scenario": "QP-01", "phase": "after-stop-1",
                                    "monotonic_ns": mono(), "unit": stopped, "cgroup": after1})
        report["snapshots"].append({"scenario": "QP-01", "phase": "after-stop-2",
                                    "monotonic_ns": mono(), "unit": stable, "cgroup": after2})
        if not quiescent:
            raise Incomplete("QP-01 did not satisfy the complete quiescence predicate")
        cleanup = _stop_and_cleanup(name, initial, endpoint, ready_path, run_dir_fd, report, already_stopped=True, cgroup_empty_confirmed=True)
        report["cleanup"]["resources"].append(cleanup)
        report["scenarios"].append({"id": "QP-01", "status": "INCOMPLETE",
                                    "decision": "ABORT_NOT_QUIESCENT",
                                    "reason": "systemd/cgroup lifecycle passed, but descriptor non-escape proof is pending QP-08/QP-09"})
        if not cleanup["endpoint_removed"] or not cleanup["cgroup_empty"]:
            raise Incomplete("QP-01 cleanup was not confirmed")

        # QP-02: child exists in the same service cgroup before listener creation.
        name2 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial2, endpoint2, ready2 = _start_fixture(name2, run_dir, hold_child=True)
        report["unit_identity"][name2] = initial2
        update_gate_marker(marker, run_id, name2, initial2, "unit-started")
        before2 = cgroup_events(mount, initial2["ControlGroup"])
        if before2["values"]["populated"] != 1:
            raise Incomplete("QP-02 did not observe the helper in a populated service cgroup")
        systemd_stop(name2)
        stopped2 = wait_inactive(name2, time.monotonic() + STOP_TIMEOUT + 3)
        after2 = cgroup_events(mount, initial2["ControlGroup"])
        stable2 = unit_snapshot(name2)
        passed2 = (
            stopped2["ActiveState"] == "inactive" and after2["values"]["populated"] == 0
            and stable2["InvocationID"] == initial2["InvocationID"]
            and stable2["Job"][0] == 0
        )
        cleanup2 = _stop_and_cleanup(name2, initial2, endpoint2, ready2, run_dir_fd, report, already_stopped=True, cgroup_empty_confirmed=True)
        report["cleanup"]["resources"].append(cleanup2)
        if not passed2 or not cleanup2["endpoint_removed"]:
            raise Incomplete("QP-02 failed its pre-stop helper or post-stop empty-cgroup check")
        report["scenarios"].append({"id": "QP-02", "status": "INCOMPLETE",
                                    "decision": "ABORT_NOT_QUIESCENT",
                                    "reason": "helper terminated with its cgroup, but descriptor non-escape proof is pending QP-08/QP-09"})

        # QP-03: ignored SIGTERM must prevent a premature quiescent result.
        name3 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial3, endpoint3, ready3 = _start_fixture(name3, run_dir, ignore_term=True)
        report["unit_identity"][name3] = initial3
        update_gate_marker(marker, run_id, name3, initial3, "unit-started")
        systemd_stop(name3)
        transitional3, populated3 = _wait_for_deactivation(
            name3, mount, initial3["ControlGroup"], time.monotonic() + 1.5
        )
        if populated3["values"]["populated"] != 1:
            raise Incomplete("QP-03 failed to observe the live cgroup during stop")
        stopped3 = wait_inactive(name3, time.monotonic() + STOP_TIMEOUT + 5)
        empty3 = cgroup_events(mount, initial3["ControlGroup"])
        cleanup3 = _stop_and_cleanup(
            name3, initial3, endpoint3, ready3, run_dir_fd, report,
            already_stopped=True, cgroup_empty_confirmed=empty3["values"]["populated"] == 0
        )
        report["cleanup"]["resources"].append(cleanup3)
        if stopped3["ActiveState"] != "inactive" or empty3["values"]["populated"] != 0 or not cleanup3["endpoint_removed"]:
            raise Incomplete("QP-03 did not reach manager-controlled final termination")
        report["scenarios"].append({"id": "QP-03", "status": "PASS",
                                    "decision": "ABORT_NOT_QUIESCENT",
                                    "reason": "initial deadline observed deactivating + populated=1; manager later terminated fixture"})

        # QP-04: a pending stop job and populated cgroup are never quiescent.
        name4 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial4, endpoint4, ready4 = _start_fixture(name4, run_dir, ignore_term=True)
        report["unit_identity"][name4] = initial4
        update_gate_marker(marker, run_id, name4, initial4, "unit-started")
        systemd_stop(name4)
        transitional4, populated4 = _wait_for_deactivation(
            name4, mount, initial4["ControlGroup"], time.monotonic() + 1.5
        )
        if transitional4["Job"][0] == 0 or populated4["values"]["populated"] != 1:
            raise Incomplete("QP-04 did not observe a pending stop job with a populated cgroup")
        stopped4 = wait_inactive(name4, time.monotonic() + STOP_TIMEOUT + 5)
        empty4 = cgroup_events(mount, initial4["ControlGroup"])
        cleanup4 = _stop_and_cleanup(
            name4, initial4, endpoint4, ready4, run_dir_fd, report,
            already_stopped=True, cgroup_empty_confirmed=empty4["values"]["populated"] == 0
        )
        report["cleanup"]["resources"].append(cleanup4)
        if stopped4["ActiveState"] != "inactive" or empty4["values"]["populated"] != 0 or not cleanup4["endpoint_removed"]:
            raise Incomplete("QP-04 cleanup after pending stop job failed")
        report["scenarios"].append({"id": "QP-04", "status": "PASS",
                                    "decision": "ABORT_NOT_QUIESCENT",
                                    "reason": "pending Unit.Job and populated=1 observed before manager termination"})

        # QP-06: Delegate=yes must be rejected; no cgroup writes or migration.
        name6 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial6, endpoint6, ready6 = _start_fixture(name6, run_dir, delegate=True)
        update_gate_marker(marker, run_id, name6, initial6, "unit-started")
        if initial6["Delegate"] is not True:
            raise Incomplete("QP-06 negative fixture did not expose Delegate=yes")
        cleanup6 = _stop_and_cleanup(name6, initial6, endpoint6, ready6, run_dir_fd, report)
        report["cleanup"]["resources"].append(cleanup6)
        if not cleanup6["unit_inactive"] or not cleanup6["cgroup_empty"] or not cleanup6["endpoint_removed"]:
            raise Incomplete("QP-06 negative fixture cleanup failed")
        report["scenarios"].append({"id": "QP-06", "status": "INCOMPLETE",
                                    "decision": "ABORT_NOT_QUIESCENT",
                                    "reason": "Delegate=yes rejection observed; Delegate=no capability/positive control remains unverified"})

        # QP-07: parser fault matrix; malformed data is never normalized to zero.
        parser_cases = [
            (b"populated 0\n", True), (b"populated 1\n", True),
            (b"", False), (b"frozen 0\n", False),
            (b"populated 0\npopulated 1\n", False),
            (b"populated x\n", False), (b"populated 0\nunknown 1\n", False),
        ]
        parser_results = []
        for raw, expected in parser_cases:
            try:
                parsed = _parse_cgroup_events_bytes(raw)
                actual = parsed["populated"] in (0, 1)
            except Incomplete:
                actual = False
            if actual != expected:
                raise ProbeError("QP-07 cgroup.events parser fault matrix mismatch")
            parser_results.append({"input_bytes": len(raw), "accepted": actual})
        report["scenarios"].append({"id": "QP-07", "status": "INCOMPLETE",
                                    "reason": "parser fault matrix covered; partial-read, permission and live cgroup.events failure injection remain pending",
                                    "observations": parser_results})

        # QP-12: direct root restart is detected by InvocationID, not trusted.
        name12 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial12, _unused_endpoint, ready12 = _start_fixture(name12, run_dir, no_listener=True)
        report["unit_identity"][name12] = initial12
        update_gate_marker(marker, run_id, name12, initial12, "unit-started")
        bounded_run(["systemctl", "--no-block", "restart", name12], timeout=5.0)
        changed = None
        deadline12 = time.monotonic() + 8.0
        while time.monotonic() < deadline12:
            candidate = unit_snapshot(name12)
            if candidate["InvocationID"] != initial12["InvocationID"] and candidate["ActiveState"] == "active":
                changed = candidate
                break
            time.sleep(0.05)
        if changed is None:
            raise Incomplete("QP-12 restart did not produce a distinct InvocationID")
        systemd_stop(name12)
        stopped12 = wait_inactive(name12, time.monotonic() + STOP_TIMEOUT + 3)
        empty12 = cgroup_events(mount, initial12["ControlGroup"])
        cleanup12 = _stop_and_cleanup(
            name12, changed, None, ready12, run_dir_fd, report,
            already_stopped=True, cgroup_empty_confirmed=empty12["values"]["populated"] == 0
        )
        report["cleanup"]["resources"].append(cleanup12)
        if stopped12["ActiveState"] != "inactive" or not cleanup12["cgroup_empty"]:
            raise Incomplete("QP-12 cleanup failed after detected replacement")
        report["scenarios"].append({"id": "QP-12", "status": "PASS",
                                    "decision": "ABORT_NOT_QUIESCENT",
                                    "reason": "direct root restart changed InvocationID; snapshots were not combined"})

        # QP-11: second actor is rejected; after simulated supervisor/orchestrator
        # crash the lock becomes available but the sticky marker still denies
        # lifecycle requests until this harness performs explicit test cleanup.
        if _ACTIVE_SUPERVISOR is None:
            raise Incomplete("QP-11 has no active test supervisor")
        unchanged_before = unit_snapshot(name12)
        denied_second_actor = False
        try:
            _ACTIVE_SUPERVISOR.request(
                "restart", ["systemctl", "--no-block", "restart", name12],
                actor_run_id=str(uuid.uuid4()),
            )
        except PermissionError:
            denied_second_actor = True
        contender_fd = os.open(
            lock_path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
        )
        competing_lock_denied = False
        try:
            try:
                fcntl.flock(contender_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                competing_lock_denied = True
        finally:
            os.close(contender_fd)
        if not denied_second_actor or not competing_lock_denied:
            raise Incomplete("QP-11 did not reject the concurrent authorized actor")

        _ACTIVE_SUPERVISOR.crash()
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        lock_fd = None
        post_crash_fd = os.open(
            lock_path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
        )
        try:
            fcntl.flock(post_crash_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            sticky = json.loads(marker.read_text(encoding="utf-8"))
            post_crash_supervisor = _TestLifecycleSupervisor(
                post_crash_fd, marker, run_id, allow_owner=False
            )
            denied_after_crash = False
            try:
                post_crash_supervisor.request(
                    "start", ["systemctl", "--no-block", "start", name12],
                    actor_run_id=run_id,
                )
            except Incomplete:
                denied_after_crash = True
            unchanged_after = unit_snapshot(name12)
            if (
                sticky.get("run_id") != run_id or not denied_after_crash
                or unchanged_after["InvocationID"] != unchanged_before["InvocationID"]
                or unchanged_after["ActiveState"] != "inactive"
                or unchanged_after["Job"][0] != 0
            ):
                raise Incomplete("QP-11 sticky marker failed to block post-crash lifecycle")
        finally:
            fcntl.flock(post_crash_fd, fcntl.LOCK_UN)
            os.close(post_crash_fd)

        # The harness now resumes only to persist evidence and perform its
        # explicitly scoped cleanup; this is not a production recovery path.
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _ACTIVE_SUPERVISOR = _TestLifecycleSupervisor(lock_fd, marker, run_id)
        report["gate"]["qp11_second_actor_rejected"] = True
        report["gate"]["qp11_lock_released_after_simulated_crash"] = True
        report["gate"]["qp11_sticky_marker_blocked_after_crash"] = True
        report["gate"]["qp11_harness_reacquired_for_evidence_cleanup"] = True
        report["scenarios"].append({
            "id": "QP-11", "status": "PASS",
            "reason": "competing actor rejected; simulated crash released flock; sticky marker blocked a new supervisor until harness-only evidence cleanup",
            "observations": {
                "second_actor_rejected": denied_second_actor,
                "competing_lock_denied": competing_lock_denied,
                "lock_available_after_crash": True,
                "sticky_marker_retained": True,
                "post_crash_start_rejected": denied_after_crash,
                "unit_invocation_unchanged": unchanged_after["InvocationID"] == unchanged_before["InvocationID"],
                "unit_remained_inactive": unchanged_after["ActiveState"] == "inactive",
                "pending_jobs": unchanged_after["Job"][0],
            },
        })

        implemented = {item["id"] for item in report["scenarios"]}
        reasons = {
            "QP-03": "pending: stop-deadline/TimeoutStopSec race harness",
            "QP-04": "pending: deterministic pending-job injection",
            "QP-05": "pending: dual-unit identity and adapter mismatch injection",
            "QP-08": "pending: libseccomp syscall-denial fixture",
            "QP-09": "pending: seccomp FD-duplication/SCM_RIGHTS denial fixture",
            "QP-10": "pending: same-process exec/CLOEXEC helper",
            "QP-12": "pending: controlled direct-root restart and InvocationID revalidation",
            "QP-13": "pending: isolated external SCM_RIGHTS holder control",
            "QP-14": "pending: deterministic manager/supervisor failure injection",
            "QP-15": "pending: cgroup identity adapter fault injection",
        }
        for scenario_id in EXPECTED:
            if scenario_id not in implemented:
                report["scenarios"].append({"id": scenario_id, "status": "INCOMPLETE",
                                            "reason": reasons[scenario_id]})
    except Exception as exc:
        report["harness_error"] = f"{type(exc).__name__}: {exc}"
        existing = {item["id"] for item in report["scenarios"]}
        for scenario_id in EXPECTED:
            if scenario_id not in existing:
                report["scenarios"].append({"id": scenario_id, "status": "INCOMPLETE",
                                            "reason": "harness aborted before scenario execution"})
    finally:
        if run_dir_fd is not None:
            os.close(run_dir_fd)
        if run_dir is not None and report["cleanup"]["safe_to_release_gate"]:
            try:
                expected = report["sandbox"]
                current = os.stat(run_dir, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(current.st_mode)
                    or (current.st_dev, current.st_ino) != (expected["device"], expected["inode"])
                    or current.st_uid != 0 or current.st_gid != SERVICE_GID
                    or stat.S_IMODE(current.st_mode) != 0o730
                ):
                    raise Incomplete("sandbox identity/mode changed; refusing directory cleanup")
                os.rmdir(run_dir)
            except Exception as exc:
                report["cleanup"]["run_directory_preserved"] = f"{type(exc).__name__}: {exc}"
                report["cleanup"]["safe_to_release_gate"] = False

        statuses = [item["status"] for item in report["scenarios"]]
        report["overall"] = (
            "PASS" if len(statuses) == 15 and all(value == "PASS" for value in statuses)
            and report["cleanup"]["safe_to_release_gate"]
            else "FAIL" if "FAIL" in statuses or "harness_error" in report
            else "INCOMPLETE"
        )
        report["finished_monotonic_ns"] = mono()
        report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        report["counts"] = {status: statuses.count(status) for status in ("PASS", "FAIL", "INCOMPLETE")}
        report_path = BASE / f"{run_id}.json"
        report["report_path"] = str(report_path)
        persisted = False
        if BASE.exists():
            try:
                _safe_json_file(report_path, report, MAX_REPORT)
                persisted = True
                report["evidence_persisted_before_gate_release"] = True
            except Exception as exc:
                report["cleanup"]["report_persist_error"] = f"{type(exc).__name__}: {exc}"
                report["cleanup"]["safe_to_release_gate"] = False

        # The sticky marker is retained on any uncertainty. The lock file and
        # /run/atlas-qp parent remain for audit and future invocations.
        if persisted and report["cleanup"]["safe_to_release_gate"] and marker_created and marker is not None:
            try:
                os.unlink(marker)
                report["gate"]["marker_removed_after_cleanup"] = True
                _rewrite_json_file(report_path, report, MAX_REPORT)
            except Exception as exc:
                report["cleanup"]["safe_to_release_gate"] = False
                report["gate"]["marker_removal_error"] = f"{type(exc).__name__}: {exc}"
        if lock_fd is not None:
            if report["cleanup"]["safe_to_release_gate"]:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    return report


def _parse_cgroup_events_bytes(raw: bytes) -> dict:
    if len(raw) > MAX_CGROUP:
        raise Incomplete("cgroup.events exceeds limit")
    try:
        text = raw.decode("ascii", "strict")
    except UnicodeError as exc:
        raise Incomplete("cgroup.events is not ASCII") from exc
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[0] in result or fields[0] not in {"populated", "frozen"}:
            raise Incomplete("malformed/duplicate/unknown cgroup.events key")
        if fields[1] not in {"0", "1"}:
            raise Incomplete("invalid cgroup.events boolean")
        result[fields[0]] = int(fields[1])
    if "populated" not in result:
        raise Incomplete("missing populated")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-disposable-vm", action="store_true")
    parser.add_argument("--fixture", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--socket", help=argparse.SUPPRESS)
    parser.add_argument("--ready", help=argparse.SUPPRESS)
    parser.add_argument("--hold-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ignore-term", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-listener", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.fixture:
        if not args.socket or not args.ready:
            return 2
        return fixture_main(args)
    if not args.confirm_disposable_vm:
        print("ERROR: pass --confirm-disposable-vm only inside Atlas-VM-test", file=sys.stderr)
        return 2
    report = run_probe(args)
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_REPORT:
        print("ERROR: report exceeds 1 MiB; evidence preserved only in bounded stdout", file=sys.stderr)
        return 2
    print(raw.decode("utf-8"))
    return 0 if report.get("overall") == "PASS" else 1 if report.get("overall") == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
