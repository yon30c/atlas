#!/usr/bin/env python3
"""A-IPC-05 listener-quiescence probe (disposable Atlas-VM-test only).

This runner is deliberately fail-closed. It never operates on a pre-existing
unit, never installs persistent systemd configuration, and never performs
stale-path recovery. Scenarios without a complete executable oracle remain
INCOMPLETE; they are never represented as PASS.
"""
from __future__ import annotations

import argparse
import array
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


def manager_call(adapter, *args):
    try:
        return adapter(*args)
    except Exception as exc:
        raise Incomplete(f"system manager query failed: {type(exc).__name__}") from exc


def dbus_property(path: str, interface: str, name: str, expected_type: str):
    result = manager_call(busctl_json,
        "get-property", BUS, path, interface, name
    )
    if result["type"] != expected_type:
        raise Incomplete(
            f"D-Bus property {interface}.{name} has type "
            f"{result['type']!r}, expected {expected_type!r}"
        )
    return result["data"]


def unit_path(name: str) -> str:
    result = manager_call(
        busctl_json, "call", BUS, MANAGER, MANAGER_IFACE, "GetUnit", "s", name
    )
    if result["type"] != "o" or not isinstance(result["data"], str):
        raise Incomplete("GetUnit did not return one object path")
    if not result["data"].startswith("/org/freedesktop/systemd1/unit/"):
        raise Incomplete("GetUnit returned an unexpected object path")
    return result["data"]


def list_jobs_for_unit(name: str) -> list[dict]:
    result = manager_call(busctl_json, "call", BUS, MANAGER, MANAGER_IFACE, "ListJobs")
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
                "state": row[3], "job_path": row[4], "unit_path": row[5],
            })
    return matches


def unit_is_absent(name: str) -> bool:
    result = manager_call(
        busctl_json, "call", BUS, MANAGER, MANAGER_IFACE, "ListUnitsByNames", "as", "1", name
    )
    if result["type"] != "a(ssssssouso)" or not isinstance(result["data"], list):
        raise Incomplete("ListUnitsByNames returned an unexpected signature or shape")
    return not result["data"]


def assert_unit_absent(name: str) -> None:
    if not unit_is_absent(name):
        raise Incomplete(f"random fixture unit name already exists: {name}")


def wait_unit_absent(name: str, deadline: float) -> None:
    while time.monotonic() < deadline:
        if unit_is_absent(name):
            return
        time.sleep(0.05)
    raise Incomplete("systemd retained a reference to the stopped transient fixture")


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
        "MainPID": dbus_property(path, SERVICE_IFACE, "MainPID", "u"),
        "KillMode": dbus_property(path, SERVICE_IFACE, "KillMode", "s"),
        "Restart": dbus_property(path, SERVICE_IFACE, "Restart", "s"),
        "User": dbus_property(path, SERVICE_IFACE, "User", "s"),
        "Group": dbus_property(path, SERVICE_IFACE, "Group", "s"),
        "UID": dbus_property(path, SERVICE_IFACE, "UID", "u"),
        "GID": dbus_property(path, SERVICE_IFACE, "GID", "u"),
        "CapabilityBoundingSet": dbus_property(path, SERVICE_IFACE, "CapabilityBoundingSet", "t"),
        "AmbientCapabilities": dbus_property(path, SERVICE_IFACE, "AmbientCapabilities", "t"),
        "NoNewPrivileges": dbus_property(path, SERVICE_IFACE, "NoNewPrivileges", "b"),
        "ProtectControlGroups": dbus_property(path, SERVICE_IFACE, "ProtectControlGroups", "b"),
        "Delegate": dbus_property(path, RESOURCE_IFACE, "Delegate", "b"),
        "DelegateControllers": dbus_property(path, RESOURCE_IFACE, "DelegateControllers", "as"),
        "DelegateSubgroup": dbus_property(path, RESOURCE_IFACE, "DelegateSubgroup", "s"),
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


def cgroup_identity(mount_root: Path, control_group: str) -> dict:
    if not control_group.startswith("/") or ".." in Path(control_group).parts:
        raise Incomplete("systemd returned an unsafe ControlGroup path")
    path = mount_root / control_group.lstrip("/")
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise Incomplete("ControlGroup does not resolve to a directory")
        return {"control_group": control_group, "st_dev": info.st_dev, "st_ino": info.st_ino}
    finally:
        os.close(fd)


def require_cgroup_identity(expected: dict, observed: dict) -> None:
    if expected != observed:
        raise Incomplete("cgroup identity mismatch; refusing to use the observed cgroup")


def read_bounded_chunks(read_call, limit: int) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = read_call(min(1024, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise Incomplete(f"cgroup.events exceeds {limit} bytes")
    return b"".join(chunks)


def cgroup_events(mount_root: Path, control_group: str) -> dict:
    if not control_group.startswith("/") or ".." in Path(control_group).parts:
        raise Incomplete("systemd returned an unsafe ControlGroup path")
    path = mount_root / control_group.lstrip("/") / "cgroup.events"
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            raw = read_bounded_chunks(lambda size: os.read(fd, size), MAX_CGROUP)
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


def _json_no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _json_reject_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def read_bounded_json_file(path: Path, *, expected_uid: int | None = None,
                           expected_gid: int | None = None, limit: int = 4096) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or (expected_uid is not None and info.st_uid != expected_uid)
            or (expected_gid is not None and info.st_gid != expected_gid)
            or info.st_size > limit
        ):
            raise Incomplete("JSON evidence file identity, mode or size is invalid")
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise Incomplete("JSON evidence file exceeds its byte limit")
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_json_no_duplicate_keys,
            parse_constant=_json_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise Incomplete("JSON evidence file is malformed or ambiguous") from exc
    if not isinstance(value, dict):
        raise Incomplete("JSON evidence root must be an object")
    return value


class _TestLifecycleSupervisor:
    """Harness-only lifecycle gate; never imported by the Atlas runtime."""

    def __init__(self, lock_fd: int, marker: Path, run_id: str, *,
                 allow_owner: bool = True, units: set[str] | None = None):
        self.lock_fd = lock_fd
        self.marker = marker
        self.run_id = run_id
        self.allow_owner = allow_owner
        self.units = set(units or ())
        self.active = True

    def request(self, action: str, argv: list[str], *, actor_run_id: str) -> bytes:
        if not self.active:
            raise Incomplete("test lifecycle supervisor is unavailable")
        if action not in {"start", "stop", "restart"}:
            raise Incomplete("test lifecycle supervisor received an unsupported action")
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            marker_data = read_bounded_json_file(self.marker, expected_uid=0, expected_gid=0)
        except (OSError, json.JSONDecodeError) as exc:
            raise Incomplete("test lifecycle supervisor cannot verify its gate") from exc
        if marker_data.get("schema") != SCHEMA or marker_data.get("run_id") != self.run_id:
            raise Incomplete("test lifecycle supervisor marker ownership mismatch")
        if not self.allow_owner:
            raise Incomplete("sticky maintenance marker blocks lifecycle until explicit manual recovery")
        if actor_run_id != self.run_id:
            raise PermissionError("second authorized actor rejected by maintenance gate")
        if not argv:
            raise Incomplete("test lifecycle supervisor received an empty command")
        if action == "start":
            if argv[0] != "systemd-run":
                raise Incomplete("start requests must use systemd-run")
            unit_args = [item.split("=", 1)[1] for item in argv if item.startswith("--unit=")]
            if len(unit_args) != 1 or not unit_args[0].startswith("atlas-qp-") or not unit_args[0].endswith(".service"):
                raise Incomplete("start request does not name one owned transient fixture")
            if unit_args[0] in self.units:
                raise Incomplete("test lifecycle supervisor refuses duplicate fixture start")
            result = bounded_run(argv, timeout=8.0)
            self.units.add(unit_args[0])
            return result
        if (
            argv[0] != "systemctl" or len(argv) != 4
            or argv[1] != "--no-block" or argv[2] != action
            or argv[3] not in self.units
        ):
            raise Incomplete("lifecycle request is outside the registered fixture allowlist")
        return bounded_run(argv, timeout=8.0)

    def crash(self) -> None:
        self.active = False


_ACTIVE_SUPERVISOR: _TestLifecycleSupervisor | None = None
_ACTIVE_RUN_ID: str | None = None
_ACTIVE_FIXTURES: dict[str, dict] = {}
_CLEANED_FIXTURES: set[str] = set()
_SANDBOX_DIRS: list[dict] = []
_OPEN_DIR_FDS: list[int] = []


def register_sandbox_dir(path: Path) -> None:
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode):
        raise Incomplete("sandbox registration target is not a directory")
    _SANDBOX_DIRS.append({
        "path": path, "device": info.st_dev, "inode": info.st_ino,
        "uid": info.st_uid, "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
    })


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


class _ScmpArgCmp(__import__("ctypes").Structure):
    _fields_ = [("arg", __import__("ctypes").c_uint),
                ("op", __import__("ctypes").c_uint),
                ("datum_a", __import__("ctypes").c_uint64),
                ("datum_b", __import__("ctypes").c_uint64)]


def install_seccomp_denials(*, deny_fork: bool = False, deny_fd_escape: bool = False) -> None:
    import ctypes
    library_name = ctypes.util.find_library("seccomp")
    if not library_name:
        raise Incomplete("libseccomp is unavailable in fixture")
    lib = ctypes.CDLL(library_name, use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_rule_add.restype = ctypes.c_int
    lib.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint,
        ctypes.POINTER(_ScmpArgCmp),
    ]
    lib.seccomp_rule_add_array.restype = ctypes.c_int
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_load.restype = ctypes.c_int
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.restype = None
    action_allow = 0x7FFF0000
    action_deny = 0x00050000 | errno.EPERM
    context = lib.seccomp_init(action_allow)
    if not context:
        raise Incomplete("seccomp_init failed")
    try:
        names = []
        if deny_fork:
            names.extend((b"fork", b"vfork", b"clone", b"clone3"))
        if deny_fd_escape:
            names.extend((b"dup", b"dup2", b"dup3", b"sendmsg", b"recvmsg", b"sendmmsg", b"recvmmsg"))
        for name in names:
            number = lib.seccomp_syscall_resolve_name(name)
            if number < 0 or lib.seccomp_rule_add(context, action_deny, number, 0) != 0:
                raise Incomplete(f"cannot install seccomp denial for {name.decode()}")
        if deny_fd_escape:
            fcntl_number = lib.seccomp_syscall_resolve_name(b"fcntl")
            if fcntl_number < 0:
                raise Incomplete("cannot resolve fcntl for seccomp")
            for command in (fcntl.F_DUPFD, fcntl.F_DUPFD_CLOEXEC):
                comparison = _ScmpArgCmp(1, 4, command, 0)  # SCMP_CMP_EQ
                if lib.seccomp_rule_add_array(
                    context, action_deny, fcntl_number, 1, ctypes.byref(comparison)
                ) != 0:
                    raise Incomplete("cannot install argument-scoped fcntl seccomp rule")
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
            raise Incomplete("PR_SET_NO_NEW_PRIVS failed before seccomp")
        if lib.seccomp_load(context) != 0:
            raise Incomplete("seccomp_load failed")
    finally:
        lib.seccomp_release(context)


def _raw_syscall_errno(libc, number: int, *arguments) -> int:
    ctypes.set_errno(0)
    result = libc.syscall(ctypes.c_long(number), *arguments)
    if result != -1:
        return 0
    return ctypes.get_errno()


def run_fd_policy_checks(listener: socket.socket, *, deny_fork: bool, deny_fd_escape: bool) -> dict:
    if platform.machine() != "x86_64":
        raise Incomplete("syscall fault-injection numbers are defined only for x86_64")
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    libc.vfork.restype = ctypes.c_int
    observations = {}
    install_seccomp_denials(deny_fork=deny_fork, deny_fd_escape=deny_fd_escape)
    if deny_fork:
        results = {}
        try:
            child = os.fork()
        except OSError as exc:
            results["fork"] = exc.errno
        else:
            if child == 0:
                os._exit(91)
            os.kill(child, signal.SIGKILL)
            os.waitpid(child, 0)
            results["fork"] = 0
        try:
            child = libc.vfork()
        except OSError as exc:
            results["vfork"] = exc.errno
        else:
            if child == 0:
                os._exit(92)
            if child > 0:
                os.waitpid(child, 0)
                results["vfork"] = 0
            else:
                results["vfork"] = ctypes.get_errno()
        results["clone"] = _raw_syscall_errno(
            libc, 56, ctypes.c_ulong(0), ctypes.c_void_p(0),
            ctypes.c_void_p(0), ctypes.c_void_p(0), ctypes.c_ulong(0),
        )
        results["clone3"] = _raw_syscall_errno(
            libc, 435, ctypes.c_void_p(0), ctypes.c_size_t(0),
        )
        observations["fork_denials"] = results
        if any(value != errno.EPERM for value in results.values()):
            raise Incomplete("QP-08 syscall denial did not return EPERM for every fork path")
    if deny_fd_escape:
        fd = listener.fileno()
        results = {
            "dup": _raw_syscall_errno(libc, 32, ctypes.c_int(fd)),
            "dup2": _raw_syscall_errno(libc, 33, ctypes.c_int(fd), ctypes.c_int(10000)),
            "dup3": _raw_syscall_errno(libc, 292, ctypes.c_int(fd), ctypes.c_int(10001), ctypes.c_int(0)),
            "fcntl_dupfd": _raw_syscall_errno(libc, 72, ctypes.c_int(fd), ctypes.c_int(fcntl.F_DUPFD), ctypes.c_int(10002)),
            "fcntl_dupfd_cloexec": _raw_syscall_errno(libc, 72, ctypes.c_int(fd), ctypes.c_int(fcntl.F_DUPFD_CLOEXEC), ctypes.c_int(10003)),
            "sendmsg": _raw_syscall_errno(libc, 46, ctypes.c_int(-1), ctypes.c_void_p(0), ctypes.c_int(0)),
            "recvmsg": _raw_syscall_errno(libc, 47, ctypes.c_int(-1), ctypes.c_void_p(0), ctypes.c_int(0)),
            "sendmmsg": _raw_syscall_errno(libc, 307, ctypes.c_int(-1), ctypes.c_void_p(0), ctypes.c_uint(0), ctypes.c_uint(0)),
            "recvmmsg": _raw_syscall_errno(libc, 299, ctypes.c_int(-1), ctypes.c_void_p(0), ctypes.c_uint(0), ctypes.c_uint(0), ctypes.c_void_p(0)),
        }
        if fcntl.fcntl(fd, fcntl.F_GETFD) < 0:
            raise Incomplete("non-dup fcntl operation was unexpectedly blocked")
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, b"ok")
            if os.read(read_fd, 2) != b"ok":
                raise Incomplete("read/write control channel failed under FD policy")
        finally:
            os.close(read_fd)
            os.close(write_fd)
        observations["fd_escape_denials"] = results
        observations["fcntl_getfd_allowed"] = True
        observations["read_write_control_allowed"] = True
        if any(value != errno.EPERM for value in results.values()):
            raise Incomplete("QP-09 FD escape syscall denial did not return EPERM")
    return observations


def fixture_main(args: argparse.Namespace) -> int:
    """Unprivileged systemd service fixture; never used against Atlas."""
    if args.exec_helper:
        fd_closed = False
        try:
            os.fstat(args.listener_fd)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise
            fd_closed = True
        info = os.stat(args.socket, follow_symlinks=False)
        ready = {
            "pid": os.getpid(), "original_pid": args.original_pid,
            "fd": args.listener_fd, "listener_fd_closed": fd_closed,
            "exec_same_pid": os.getpid() == args.original_pid,
            "device": info.st_dev, "inode": info.st_ino,
            "uid": info.st_uid, "gid": info.st_gid,
            "mode": stat.S_IMODE(info.st_mode), "exec_helper": True,
        }
        fd = os.open(args.ready, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC, 0o600)
        try:
            os.write(fd, json.dumps(ready, sort_keys=True).encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)
        while True:
            signal.pause()
    if args.fd_holder:
        control = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        os.umask(0o177)
        control.bind(args.control)
        os.chmod(args.control, 0o666)
        control.listen(1)
        control_info = os.stat(args.control, follow_symlinks=False)
        holder_ready = {
            "pid": os.getpid(), "fd": None, "holder_ready": True,
            "device": control_info.st_dev, "inode": control_info.st_ino,
            "uid": control_info.st_uid, "gid": control_info.st_gid,
            "mode": stat.S_IMODE(control_info.st_mode),
        }
        ready_fd = os.open(args.ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        try:
            os.write(ready_fd, json.dumps(holder_ready, sort_keys=True).encode("ascii"))
            os.fsync(ready_fd)
        finally:
            os.close(ready_fd)
        connection, _address = control.accept()
        try:
            _data, ancillary, _flags, _address = connection.recvmsg(
                1, socket.CMSG_SPACE(array.array("i").itemsize * 2)
            )
        finally:
            connection.close()
            control.close()
        received_fds = []
        for level, kind, payload in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                descriptors = array.array("i")
                descriptors.frombytes(payload[:len(payload) - (len(payload) % descriptors.itemsize)])
                received_fds.extend(descriptors.tolist())
        if len(received_fds) != 1:
            raise Incomplete("QP-13 holder did not receive exactly one listener FD")
        received_fd = received_fds[0]
        held = socket.socket(fileno=received_fd)
        try:
            held_type = held.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
            accepting = held.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
            fd_info = os.fstat(received_fd)
            received = {
                "pid": os.getpid(), "fd": received_fd, "device": fd_info.st_dev,
                "inode": fd_info.st_ino, "socket_type": held_type,
                "accepting": accepting, "fd_open": True,
            }
        finally:
            held.detach()
        received_fd_file = os.open(args.received, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        try:
            os.write(received_fd_file, json.dumps(received, sort_keys=True).encode("ascii"))
            os.fsync(received_fd_file)
        finally:
            os.close(received_fd_file)
        while True:
            signal.pause()

    listener = None
    child = None
    child_filter_confirmed = False
    try:
        if args.hold_child:
            child_ready_read, child_ready_write = os.pipe()
            child = os.fork()
            if child == 0:
                os.close(child_ready_read)
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                if args.deny_fork or args.deny_fd_escape:
                    install_seccomp_denials(
                        deny_fork=args.deny_fork,
                        deny_fd_escape=args.deny_fd_escape,
                    )
                os.write(child_ready_write, b"1")
                os.close(child_ready_write)
                while True:
                    signal.pause()
            os.close(child_ready_write)
            child_filter_confirmed = os.read(child_ready_read, 1) == b"1"
            os.close(child_ready_read)
            if not child_filter_confirmed:
                raise Incomplete("QP-02 child did not confirm pre-listener seccomp policy")
        if args.ignore_term:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        ready = {"pid": os.getpid(), "fd": None, "child_pid": child,
                 "child_filter_confirmed": child_filter_confirmed}
        if not args.no_listener:
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            listener.set_inheritable(False)
            os.umask(0o177)
            listener.bind(args.socket)
            listener.listen(1)
            if args.transfer_fd_to:
                with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as transfer:
                    transfer.connect(args.transfer_fd_to)
                    transfer.sendmsg(
                        [b"listener-fd"],
                        [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [listener.fileno()]))],
                    )
            info = os.stat(args.socket, follow_symlinks=False)
            if args.exec_check:
                original_pid = os.getpid()
                original_fd = listener.detach()
                exec_fd = fcntl.fcntl(original_fd, fcntl.F_DUPFD_CLOEXEC, 200)
                os.close(original_fd)
                os.execve(sys.executable, [
                    sys.executable, "-I", str(Path(__file__).resolve()),
                    "--fixture", "--exec-helper", "--listener-fd", str(exec_fd),
                    "--original-pid", str(original_pid), "--socket", args.socket,
                    "--ready", args.ready,
                ], {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
            ready.update({
                "fd": listener.fileno(), "device": info.st_dev, "inode": info.st_ino,
                "uid": info.st_uid, "gid": info.st_gid,
                "mode": stat.S_IMODE(info.st_mode),
                "socket_type": listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE),
                "accepting": listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN),
                "cloexec": not os.get_inheritable(listener.fileno()),
            })
            if args.deny_fork or args.deny_fd_escape:
                ready["fd_policy"] = run_fd_policy_checks(
                    listener, deny_fork=args.deny_fork,
                    deny_fd_escape=args.deny_fd_escape,
                )
        try:
            status = {}
            for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
                if line.startswith(("CapEff:", "CapBnd:")):
                    key, value = line.split(":", 1)
                    status[key] = int(value.strip(), 16)
            _cg_root, cg_mount = cgroup_mount()
            cgroup_line = next(
                line for line in Path("/proc/self/cgroup").read_text(encoding="ascii").splitlines()
                if line.startswith("0::")
            )
            own_cgroup = cgroup_line[3:]
            own_cgroup_path = cg_mount / own_cgroup.lstrip("/")
            ready["cap_eff"] = status.get("CapEff")
            ready["cap_bnd"] = status.get("CapBnd")
            ready["cap_sys_admin"] = bool((status.get("CapEff", 0) >> 21) & 1)
            ready["cgroup_dir_write_access"] = os.access(
                own_cgroup_path, os.W_OK, effective_ids=True
            )
        except (OSError, StopIteration, ValueError) as exc:
            raise Incomplete(f"fixture capability/cgroup evidence unavailable: {type(exc).__name__}") from exc
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
    if platform.machine() != "x86_64":
        raise Incomplete("the syscall fault-injection profile requires x86_64")
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


def validate_report_bounds(report: dict) -> None:
    for scenario in report.get("scenarios", []):
        raw_scenario = json.dumps(
            scenario, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        if len(raw_scenario) > MAX_SCENARIO:
            raise Incomplete("one scenario evidence object exceeds 32 KiB")
    raw_report = json.dumps(
        report, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(raw_report) > MAX_REPORT:
        raise Incomplete("complete evidence report exceeds 1 MiB")


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


def _start_fixture(name: str, run_dir: Path, *, hold_child=False, ignore_term=False,
                   delegate=False, no_listener=False, uid=SERVICE_UID, gid=SERVICE_GID,
                   deny_fork=False, deny_fd_escape=False, exec_check=False,
                   no_new_privs=False, protect_cgroups=False, drop_caps=False,
                   fd_holder=False, control_path: Path | None = None,
                   received_path: Path | None = None,
                   transfer_fd_to: Path | None = None) -> tuple[dict, Path | None, Path]:
    assert_unit_absent(name)
    socket_path = run_dir / f"{name}.sock"
    ready_path = run_dir / f"{name}.ready"
    properties = [
        "--property=Type=exec", "--property=KillMode=control-group",
        "--property=Restart=no", f"--property=Delegate={'yes' if delegate else 'no'}",
        "--property=TimeoutStopSec=6s", f"--uid={uid}", f"--gid={gid}",
    ]
    if no_new_privs:
        properties.append("--property=NoNewPrivileges=yes")
    if protect_cgroups:
        properties.append("--property=ProtectControlGroups=yes")
    if drop_caps:
        properties.append("--property=CapabilityBoundingSet=")
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
    if deny_fork:
        command.append("--deny-fork")
    if deny_fd_escape:
        command.append("--deny-fd-escape")
    if exec_check:
        command.append("--exec-check")
    if fd_holder:
        if control_path is None or received_path is None:
            raise Incomplete("QP-13 holder requires explicit control and received paths")
        command.extend(["--fd-holder", "--control", str(control_path), "--received", str(received_path)])
    if transfer_fd_to is not None:
        command.extend(["--transfer-fd-to", str(transfer_fd_to)])
    if _ACTIVE_SUPERVISOR is None or _ACTIVE_RUN_ID is None:
        raise Incomplete("no active test lifecycle supervisor")
    _ACTIVE_SUPERVISOR.request("start", command, actor_run_id=_ACTIVE_RUN_ID)
    fixture_socket_path = control_path if fd_holder else (None if no_listener else socket_path)
    fixture_dir_fd = os.open(run_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    _OPEN_DIR_FDS.append(fixture_dir_fd)
    _ACTIVE_FIXTURES[name] = {
        "name": name, "run_dir": run_dir, "dir_fd": fixture_dir_fd,
        "socket_path": fixture_socket_path, "ready_path": ready_path,
        "uid": uid, "gid": gid, "initial": None, "unit_ref": False,
    }
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        try:
            ready = read_bounded_json_file(ready_path, expected_uid=uid, expected_gid=gid)
            break
        except FileNotFoundError:
            time.sleep(0.05)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise Incomplete("fixture readiness record is malformed") from exc
    else:
        raise Incomplete("fixture did not publish readiness")
    snap = unit_snapshot(name)
    if snap["MainPID"] <= 0 or ready.get("pid") != snap["MainPID"]:
        raise Incomplete("fixture readiness PID differs from systemd MainPID")
    _ACTIVE_FIXTURES[name]["initial"] = snap
    manager_call(busctl_json, "call", BUS, MANAGER, MANAGER_IFACE, "RefUnit", "s", name)
    _ACTIVE_FIXTURES[name]["unit_ref"] = True
    if snap["Delegate"] != delegate:
        raise Incomplete("systemd Delegate property differs from requested fixture")
    expected_user = pwd.getpwuid(uid).pw_name
    expected_group = grp.getgrgid(gid).gr_name
    if (
        snap["User"] != expected_user or snap["Group"] != expected_group
        or snap["UID"] != uid or snap["GID"] != gid
    ):
        raise Incomplete("systemd fixture User/Group/UID/GID identity differs from requested identity")
    if snap["ControlGroup"] == "":
        raise Incomplete("systemd returned an empty ControlGroup")
    if exec_check and (
        not ready.get("exec_helper") or not ready.get("exec_same_pid")
        or not ready.get("listener_fd_closed")
    ):
        raise Incomplete("QP-10 exec helper did not confirm same PID and closed listener FD")
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
            if ready_path is None:
                raise Incomplete("fixture endpoint has no identity record; preserving it")
            fixture_record = _ACTIVE_FIXTURES.get(name, {})
            ready = read_bounded_json_file(
                ready_path, expected_uid=fixture_record.get("uid"),
                expected_gid=fixture_record.get("gid"),
            )
            name_only = socket_path.name
            current_info = os.stat(name_only, dir_fd=run_dir_fd, follow_symlinks=False)
            if (
                not stat.S_ISSOCK(current_info.st_mode)
                or (current_info.st_dev, current_info.st_ino) != (ready["device"], ready["inode"])
                or current_info.st_uid != ready["uid"]
                or current_info.st_gid != ready["gid"]
                or stat.S_IMODE(current_info.st_mode) != ready["mode"]
            ):
                raise Incomplete("fixture endpoint identity/type/owner/mode changed; preserving it")
            os.unlink(name_only, dir_fd=run_dir_fd)
            cleanup["endpoint_removed"] = True
        if ready_path is not None:
            try:
                os.unlink(ready_path.name, dir_fd=run_dir_fd)
            except FileNotFoundError:
                pass
        fixture_record = _ACTIVE_FIXTURES.get(name, {})
        if fixture_record.get("unit_ref"):
            manager_call(busctl_json, "call", BUS, MANAGER, MANAGER_IFACE, "UnrefUnit", "s", name)
            fixture_record["unit_ref"] = False
            cleanup["unit_unref_confirmed"] = True
        wait_unit_absent(name, time.monotonic() + 3.0)
        cleanup["unit_unloaded"] = True
        if (
            cleanup["unit_inactive"] and cleanup["cgroup_empty"]
            and (socket_path is None or cleanup["endpoint_removed"])
        ):
            _CLEANED_FIXTURES.add(name)
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
    global _ACTIVE_SUPERVISOR, _ACTIVE_RUN_ID
    _ACTIVE_SUPERVISOR = None
    _ACTIVE_RUN_ID = None
    _ACTIVE_FIXTURES.clear()
    _CLEANED_FIXTURES.clear()
    _SANDBOX_DIRS.clear()
    _OPEN_DIR_FDS.clear()
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
        _OPEN_DIR_FDS.append(run_dir_fd)
        run_dir_info = os.fstat(run_dir_fd)
        register_sandbox_dir(run_dir)
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
        initial, endpoint, ready_path = _start_fixture(
            name, run_dir, deny_fork=True, deny_fd_escape=True
        )
        report["unit_identity"][name] = initial
        update_gate_marker(marker, run_id, name, initial, "unit-started")
        before_identity = cgroup_identity(mount, initial["ControlGroup"])
        before = cgroup_events(mount, initial["ControlGroup"])
        report["snapshots"].append({"scenario": "QP-01", "phase": "before-stop",
                                    "monotonic_ns": mono(), "unit": initial, "cgroup": before})
        systemd_stop(name)
        stopped = wait_inactive(name, time.monotonic() + STOP_TIMEOUT + 3)
        after1 = cgroup_events(mount, initial["ControlGroup"])
        after2 = cgroup_events(mount, initial["ControlGroup"])
        stable = unit_snapshot(name)
        after_identity = cgroup_identity(mount, stable["ControlGroup"])
        require_cgroup_identity(before_identity, after_identity)
        quiescent = (
            stopped["ActiveState"] == "inactive" and stopped["Job"][0] == 0
            and stable["MainPID"] == 0 and stopped["MainPID"] == 0
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
        policy01 = read_bounded_json_file(ready_path, expected_uid=SERVICE_UID, expected_gid=SERVICE_GID)["fd_policy"]
        cleanup = _stop_and_cleanup(name, initial, endpoint, ready_path, run_dir_fd, report, already_stopped=True, cgroup_empty_confirmed=True)
        report["cleanup"]["resources"].append(cleanup)
        report["scenarios"].append({"id": "QP-01", "status": "PASS",
                                    "decision": "QUIESCENT",
                                    "reason": "listener closed by service; fork/duplication/SCM_RIGHTS paths denied; manager inactive and two correlated cgroup snapshots populated=0",
                                    "observations": {"fd_policy": policy01, "stable_invocation": stable["InvocationID"] == initial["InvocationID"],
                                                     "cgroup_identity": before_identity}})
        if not cleanup["endpoint_removed"] or not cleanup["cgroup_empty"]:
            raise Incomplete("QP-01 cleanup was not confirmed")

        # QP-02: child exists in the same service cgroup before listener creation.
        name2 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial2, endpoint2, ready2 = _start_fixture(
            name2, run_dir, hold_child=True, deny_fork=True, deny_fd_escape=True
        )
        report["unit_identity"][name2] = initial2
        update_gate_marker(marker, run_id, name2, initial2, "unit-started")
        before_identity2 = cgroup_identity(mount, initial2["ControlGroup"])
        before2 = cgroup_events(mount, initial2["ControlGroup"])
        if before2["values"]["populated"] != 1:
            raise Incomplete("QP-02 did not observe the helper in a populated service cgroup")
        systemd_stop(name2)
        stopped2 = wait_inactive(name2, time.monotonic() + STOP_TIMEOUT + 3)
        after2 = cgroup_events(mount, initial2["ControlGroup"])
        stable2 = unit_snapshot(name2)
        after_identity2 = cgroup_identity(mount, stable2["ControlGroup"])
        require_cgroup_identity(before_identity2, after_identity2)
        passed2 = (
            stopped2["ActiveState"] == "inactive" and after2["values"]["populated"] == 0
            and stopped2["MainPID"] == 0 and stable2["MainPID"] == 0
            and stable2["InvocationID"] == initial2["InvocationID"]
            and stable2["Job"][0] == 0
        )
        ready2_data = read_bounded_json_file(
            ready2, expected_uid=SERVICE_UID, expected_gid=SERVICE_GID
        )
        policy02 = ready2_data["fd_policy"]
        cleanup2 = _stop_and_cleanup(name2, initial2, endpoint2, ready2, run_dir_fd, report, already_stopped=True, cgroup_empty_confirmed=True)
        report["cleanup"]["resources"].append(cleanup2)
        if not passed2 or not cleanup2["endpoint_removed"]:
            raise Incomplete("QP-02 failed its pre-stop helper or post-stop empty-cgroup check")
        report["scenarios"].append({"id": "QP-02", "status": "PASS",
                                    "decision": "QUIESCENT",
                                    "reason": "pre-listener child was contained in the service cgroup; post-listener fork/duplication/SCM_RIGHTS paths denied; stop emptied the correlated cgroup",
                                    "observations": {"fd_policy": policy02, "helper_preexisted_listener": True,
                                                     "child_pid": ready2_data["child_pid"],
                                                     "child_filter_confirmed": ready2_data["child_filter_confirmed"],
                                                     "invocation_unchanged": stable2["InvocationID"] == initial2["InvocationID"],
                                                     "cgroup_identity": before_identity2}})

        # QP-03: ignored SIGTERM must prevent a premature quiescent result.
        name3 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial3, endpoint3, ready3 = _start_fixture(name3, run_dir, ignore_term=True)
        report["unit_identity"][name3] = initial3
        update_gate_marker(marker, run_id, name3, initial3, "unit-started")
        systemd_stop(name3)
        transitional3, populated3 = _wait_for_deactivation(
            name3, mount, initial3["ControlGroup"], time.monotonic() + 1.5
        )
        if populated3["values"]["populated"] != 1 or transitional3["Job"][0] == 0:
            raise Incomplete("QP-03 failed to observe deactivation, a pending stop job and a live cgroup")
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

        # QP-05: distinct SERVICE/OTHER fixtures and an adapter-only identity mismatch.
        other_dir = BASE / f"{run_id}-other"
        os.mkdir(other_dir, 0o730)
        os.chown(other_dir, 0, OTHER_GID)
        os.chmod(other_dir, 0o730)
        register_sandbox_dir(other_dir)
        name5a = f"atlas-qp-{secrets.token_hex(6)}.service"
        name5b = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial5a, _endpoint5a, ready5a = _start_fixture(name5a, run_dir, no_listener=True)
        initial5b, _endpoint5b, ready5b = _start_fixture(
            name5b, other_dir, no_listener=True, uid=OTHER_UID, gid=OTHER_GID
        )
        report["unit_identity"][name5a] = initial5a
        report["unit_identity"][name5b] = initial5b
        cg5a = cgroup_identity(mount, initial5a["ControlGroup"])
        cg5b = cgroup_identity(mount, initial5b["ControlGroup"])
        if cg5a["control_group"] == cg5b["control_group"] or (
            cg5a["st_dev"], cg5a["st_ino"]
        ) == (cg5b["st_dev"], cg5b["st_ino"]):
            raise Incomplete("QP-05 SERVICE and OTHER fixtures do not have distinct cgroup identities")
        mismatch_rejected = False
        try:
            require_cgroup_identity(cg5a, {**cg5a, "control_group": cg5a["control_group"] + ".mismatch"})
        except Incomplete:
            mismatch_rejected = True
        other_dir_fd = os.open(other_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        _OPEN_DIR_FDS.append(other_dir_fd)
        cleanup5b = _stop_and_cleanup(name5b, initial5b, None, ready5b, other_dir_fd, report)
        cleanup5a = _stop_and_cleanup(name5a, initial5a, None, ready5a, run_dir_fd, report)
        report["cleanup"]["resources"].extend([cleanup5a, cleanup5b])
        try:
            os.rmdir(other_dir)
        except OSError as exc:
            raise Incomplete("QP-05 OTHER fixture directory was not empty") from exc
        if not mismatch_rejected or not cleanup5a["unit_inactive"] or not cleanup5b["unit_inactive"]:
            raise Incomplete("QP-05 identity mismatch or fixture cleanup was not confirmed")
        report["scenarios"].append({
            "id": "QP-05", "status": "PASS",
            "reason": "SERVICE and OTHER fixtures had distinct ControlGroup inode identities; adapter mismatch was rejected before cgroup use",
            "observations": {"service_cgroup": cg5a, "other_cgroup": cg5b,
                             "adapter_mismatch_rejected": mismatch_rejected},
        })

        # QP-08: install seccomp after bind/listen and deny all fork-family paths.
        name8 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial8, endpoint8, ready8 = _start_fixture(name8, run_dir, deny_fork=True)
        report["unit_identity"][name8] = initial8
        policy8 = read_bounded_json_file(ready8, expected_uid=SERVICE_UID, expected_gid=SERVICE_GID)["fd_policy"]
        cleanup8 = _stop_and_cleanup(name8, initial8, endpoint8, ready8, run_dir_fd, report)
        report["cleanup"]["resources"].append(cleanup8)
        if not cleanup8["unit_inactive"] or not cleanup8["cgroup_empty"] or not cleanup8["endpoint_removed"]:
            raise Incomplete("QP-08 fixture cleanup failed")
        report["scenarios"].append({
            "id": "QP-08", "status": "PASS",
            "reason": "fork/vfork/clone/clone3 all returned EPERM after listener bind/listen",
            "observations": policy8,
        })

        # QP-10: execve in the same process closes the CLOEXEC listener descriptor.
        name10 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial10, endpoint10, ready10 = _start_fixture(name10, run_dir, exec_check=True)
        report["unit_identity"][name10] = initial10
        exec_evidence = read_bounded_json_file(ready10, expected_uid=SERVICE_UID, expected_gid=SERVICE_GID)
        cleanup10 = _stop_and_cleanup(name10, initial10, endpoint10, ready10, run_dir_fd, report)
        report["cleanup"]["resources"].append(cleanup10)
        if (
            not exec_evidence.get("exec_helper")
            or not exec_evidence.get("exec_same_pid")
            or not exec_evidence.get("listener_fd_closed")
            or exec_evidence.get("pid") != initial10["MainPID"]
            or not cleanup10["unit_inactive"] or not cleanup10["cgroup_empty"]
            or not cleanup10["endpoint_removed"]
        ):
            raise Incomplete("QP-10 exec/CLOEXEC evidence or cleanup failed")
        report["scenarios"].append({
            "id": "QP-10", "status": "PASS",
            "reason": "execve replaced the same process and the helper observed EBADF for the listener FD",
            "observations": exec_evidence,
        })

        # QP-09: deny duplication and ancillary-data transfer; read/write remain usable.
        name9 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial9, endpoint9, ready9 = _start_fixture(name9, run_dir, deny_fd_escape=True)
        report["unit_identity"][name9] = initial9
        policy9 = read_bounded_json_file(ready9, expected_uid=SERVICE_UID, expected_gid=SERVICE_GID)["fd_policy"]
        cleanup9 = _stop_and_cleanup(name9, initial9, endpoint9, ready9, run_dir_fd, report)
        report["cleanup"]["resources"].append(cleanup9)
        if not cleanup9["unit_inactive"] or not cleanup9["cgroup_empty"] or not cleanup9["endpoint_removed"]:
            raise Incomplete("QP-09 fixture cleanup failed")
        report["scenarios"].append({
            "id": "QP-09", "status": "PASS",
            "reason": "duplication and SCM_RIGHTS-capable syscalls returned EPERM; fcntl F_GETFD and read/write remained available",
            "observations": policy9,
        })

        # QP-06: reject Delegate=yes and prove the Delegate=no fixture has no cgroup authority.
        name6 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial6, endpoint6, ready6 = _start_fixture(name6, run_dir, delegate=True)
        update_gate_marker(marker, run_id, name6, initial6, "unit-started")
        if initial6["Delegate"] is not True:
            raise Incomplete("QP-06 negative fixture did not expose Delegate=yes")
        cleanup6 = _stop_and_cleanup(name6, initial6, endpoint6, ready6, run_dir_fd, report)
        report["cleanup"]["resources"].append(cleanup6)
        if not cleanup6["unit_inactive"] or not cleanup6["cgroup_empty"] or not cleanup6["endpoint_removed"]:
            raise Incomplete("QP-06 negative fixture cleanup failed")
        name6good = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial6good, endpoint6good, ready6good = _start_fixture(
            name6good, run_dir, delegate=False, no_new_privs=True,
            protect_cgroups=True, drop_caps=True,
        )
        report["unit_identity"][name6good] = initial6good
        ready6good_data = read_bounded_json_file(ready6good, expected_uid=SERVICE_UID, expected_gid=SERVICE_GID)
        if (
            initial6good["Delegate"] is not False
            or initial6good["User"] != pwd.getpwuid(SERVICE_UID).pw_name
            or initial6good["Group"] != grp.getgrgid(SERVICE_GID).gr_name
            or initial6good["DelegateControllers"]
            or initial6good["DelegateSubgroup"] != ""
            or initial6good["UID"] != SERVICE_UID or initial6good["GID"] != SERVICE_GID
            or initial6good["NoNewPrivileges"] is not True
            or initial6good["ProtectControlGroups"] is not True
            or initial6good["CapabilityBoundingSet"] != 0
            or initial6good["AmbientCapabilities"] != 0
            or ready6good_data.get("cap_sys_admin") is not False
            or ready6good_data.get("cgroup_dir_write_access") is not False
        ):
            raise Incomplete("QP-06 Delegate=no fixture retains unexpected cgroup authority")
        cleanup6good = _stop_and_cleanup(name6good, initial6good, endpoint6good, ready6good, run_dir_fd, report)
        report["cleanup"]["resources"].append(cleanup6good)
        if not cleanup6good["unit_inactive"] or not cleanup6good["cgroup_empty"] or not cleanup6good["endpoint_removed"]:
            raise Incomplete("QP-06 positive fixture cleanup failed")
        report["scenarios"].append({
            "id": "QP-06", "status": "PASS", "decision": "ABORT_NOT_QUIESCENT",
            "reason": "Delegate=yes rejected; Delegate=no service had no CAP_SYS_ADMIN and could not write its cgroup directory",
            "observations": {"delegate_yes_rejected": True, "delegate_no": ready6good_data},
        })

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
        partial_chunks = iter((b"popu", b"lated ", b"0\\n", b""))
        partial_read = read_bounded_chunks(lambda _size: next(partial_chunks), MAX_CGROUP)
        if partial_read != b"populated 0\\n" or _parse_cgroup_events_bytes(partial_read)["populated"] != 0:
            raise ProbeError("QP-07 partial-read accumulation failed")
        permission_rejected = False
        try:
            read_bounded_chunks(lambda _size: (_ for _ in ()).throw(PermissionError(errno.EACCES, "injected")), MAX_CGROUP)
        except PermissionError:
            permission_rejected = True
        oversize_rejected = False
        try:
            read_bounded_chunks(lambda size: b"x" * size, MAX_CGROUP)
        except Incomplete:
            oversize_rejected = True
        if not permission_rejected or not oversize_rejected:
            raise ProbeError("QP-07 permission/size fault injection was not rejected")
        parser_results.extend([
            {"partial_read_accumulated": True},
            {"permission_error_preserved": permission_rejected},
            {"oversize_rejected": oversize_rejected},
        ])
        report["scenarios"].append({"id": "QP-07", "status": "PASS",
                                    "reason": "strict parser, partial-read accumulation, permission failure and byte limit all fail closed",
                                    "observations": parser_results})

        # QP-13: deliberately transfer one listener FD to an OTHER-cgroup holder.
        other_dir13 = BASE / f"{run_id}-qp13-shared"
        os.mkdir(other_dir13, 0o1733)
        os.chown(other_dir13, 0, 0)
        os.chmod(other_dir13, 0o1733)
        register_sandbox_dir(other_dir13)
        other_dir13_fd = os.open(other_dir13, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        _OPEN_DIR_FDS.append(other_dir13_fd)
        name13_service = f"atlas-qp-{secrets.token_hex(6)}.service"
        name13_holder = f"atlas-qp-{secrets.token_hex(6)}.service"
        endpoint13 = None
        received13 = other_dir13 / f"{name13_holder}.received"
        control13 = other_dir13 / f"{name13_holder}.control"
        initial13_holder, _no_endpoint13, ready13_holder = _start_fixture(
            name13_holder, other_dir13, no_listener=True, uid=OTHER_UID, gid=OTHER_GID,
            fd_holder=True, control_path=control13, received_path=received13,
        )
        initial13_service, endpoint13, ready13_service = _start_fixture(
            name13_service, run_dir, transfer_fd_to=control13
        )
        report["unit_identity"][name13_service] = initial13_service
        report["unit_identity"][name13_holder] = initial13_holder
        deadline13 = time.monotonic() + 5.0
        while time.monotonic() < deadline13 and not received13.exists():
            time.sleep(0.02)
        if not received13.exists():
            raise Incomplete("QP-13 external holder did not publish FD receipt")
        holder_evidence13 = read_bounded_json_file(received13, expected_uid=OTHER_UID, expected_gid=OTHER_GID)
        if holder_evidence13.get("socket_type") != socket.SOCK_SEQPACKET or holder_evidence13.get("accepting") != 1 or not holder_evidence13.get("fd_open"):
            raise Incomplete("QP-13 external holder did not retain the active listener FD")
        systemd_stop(name13_service)
        stopped13 = wait_inactive(name13_service, time.monotonic() + STOP_TIMEOUT + 3)
        empty13 = cgroup_events(mount, initial13_service["ControlGroup"])
        holder_still_active13 = unit_snapshot(name13_holder)
        holder_cgroup13 = cgroup_events(mount, initial13_holder["ControlGroup"])
        if (
            stopped13["ActiveState"] != "inactive" or stopped13["Job"][0] != 0
            or stopped13["InvocationID"] != initial13_service["InvocationID"]
            or empty13["values"]["populated"] != 0
            or holder_still_active13["ActiveState"] != "active"
            or holder_still_active13["InvocationID"] != initial13_holder["InvocationID"]
            or holder_evidence13["pid"] != initial13_holder["MainPID"]
            or holder_cgroup13["values"]["populated"] != 1
        ):
            raise Incomplete("QP-13 did not demonstrate empty service cgroup with external FD holder")
        systemd_stop(name13_holder)
        stopped13_holder = wait_inactive(name13_holder, time.monotonic() + STOP_TIMEOUT + 3)
        empty13_holder = cgroup_events(mount, initial13_holder["ControlGroup"])
        cleanup13_holder = _stop_and_cleanup(
            name13_holder, initial13_holder, control13, ready13_holder,
            other_dir13_fd, report, already_stopped=True,
            cgroup_empty_confirmed=empty13_holder["values"]["populated"] == 0,
        )
        cleanup13_service = _stop_and_cleanup(
            name13_service, initial13_service, endpoint13, ready13_service,
            run_dir_fd, report, already_stopped=True,
            cgroup_empty_confirmed=empty13["values"]["populated"] == 0,
        )
        report["cleanup"]["resources"].extend([cleanup13_holder, cleanup13_service])
        if (
            stopped13_holder["ActiveState"] != "inactive"
            or stopped13_holder["Job"][0] != 0
            or stopped13_holder["InvocationID"] != initial13_holder["InvocationID"]
            or empty13_holder["values"]["populated"] != 0
            or not cleanup13_holder["endpoint_removed"]
            or not cleanup13_service["endpoint_removed"]
        ):
            raise Incomplete("QP-13 holder/service cleanup failed")
        other_dir13_cleanup_fd = os.open(other_dir13, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            os.unlink(received13.name, dir_fd=other_dir13_cleanup_fd)
        finally:
            os.close(other_dir13_cleanup_fd)
        try:
            os.rmdir(other_dir13)
        except OSError as exc:
            raise Incomplete("QP-13 external holder evidence cleanup failed") from exc
        report["scenarios"].append({
            "id": "QP-13", "status": "PASS",
            "decision": "ABORT_NOT_QUIESCENT",
            "reason": "service cgroup became empty while an OTHER-unit process retained the listener FD; holder was then terminated before endpoint cleanup",
            "observations": {
                "service_cgroup_populated_after_stop": empty13["values"]["populated"],
                "external_holder_cgroup_populated": holder_cgroup13["values"]["populated"],
                "external_holder_fd": holder_evidence13,
                "systemd_socket_activation_tested": False,
            },
        })

        # QP-14: injected manager timeout and unavailable supervisor are fail-closed.
        def failing_manager_adapter(*_args):
            raise TimeoutError("injected system-manager disconnect")
        manager_failure_rejected = False
        try:
            manager_call(failing_manager_adapter, "GetUnit")
        except Incomplete:
            manager_failure_rejected = True
        supervisor_failure_rejected = False
        failed_supervisor = _TestLifecycleSupervisor(lock_fd, marker, run_id)
        failed_supervisor.crash()
        try:
            failed_supervisor.request(
                "stop", ["systemctl", "--no-block", "stop", "atlas-qp-never.service"],
                actor_run_id=run_id,
            )
        except Incomplete:
            supervisor_failure_rejected = True
        stop_timeout_rejected = False
        try:
            bounded_run(["/bin/sleep", "1"], timeout=0.05, limit=128)
        except Incomplete:
            stop_timeout_rejected = True
        if not manager_failure_rejected or not supervisor_failure_rejected or not stop_timeout_rejected:
            raise Incomplete("QP-14 did not fail closed for manager/supervisor/timeout faults")
        report["scenarios"].append({
            "id": "QP-14", "status": "PASS",
            "reason": "injected manager failure, unavailable supervisor and bounded-command timeout were rejected without pathname mutation",
            "observations": {"manager_failure_rejected": manager_failure_rejected,
                             "supervisor_failure_rejected": supervisor_failure_rejected,
                             "command_timeout_rejected": stop_timeout_rejected,
                             "recovery_pathname_mutation_performed": False},
        })

        # QP-12: direct root restart is detected by InvocationID, not trusted.
        name12 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial12, _unused_endpoint, ready12 = _start_fixture(name12, run_dir, no_listener=True)
        report["unit_identity"][name12] = initial12
        update_gate_marker(marker, run_id, name12, initial12, "unit-started")
        # QP-15: inject cgroup identity substitutions while the real fixture cgroup exists.
        identity15 = cgroup_identity(mount, initial12["ControlGroup"])
        inode_mismatch_rejected = False
        try:
            require_cgroup_identity(identity15, {**identity15, "st_ino": identity15["st_ino"] + 1})
        except Incomplete:
            inode_mismatch_rejected = True
        path_mismatch_rejected = False
        try:
            require_cgroup_identity(identity15, {**identity15, "control_group": identity15["control_group"] + ".other"})
        except Incomplete:
            path_mismatch_rejected = True
        if not inode_mismatch_rejected or not path_mismatch_rejected:
            raise Incomplete("QP-15 cgroup identity fault injection was not rejected")
        report["scenarios"].append({
            "id": "QP-15", "status": "PASS",
            "reason": "adapter-only st_dev/st_ino and ControlGroup mismatches were rejected without changing cgroupfs",
            "observations": {"actual_identity": identity15,
                             "inode_mismatch_rejected": inode_mismatch_rejected,
                             "control_group_mismatch_rejected": path_mismatch_rejected},
        })
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
            sticky = read_bounded_json_file(marker, expected_uid=0, expected_gid=0)
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
        _ACTIVE_SUPERVISOR = _TestLifecycleSupervisor(
            lock_fd, marker, run_id, units=set(_ACTIVE_SUPERVISOR.units)
        )
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
        for scenario_id in EXPECTED:
            if scenario_id not in implemented:
                report["scenarios"].append({
                    "id": scenario_id, "status": "INCOMPLETE",
                    "reason": "scenario was not reached before harness completion",
                })
    except Exception as exc:
        report["harness_error"] = f"{type(exc).__name__}: {exc}"
        existing = {item["id"] for item in report["scenarios"]}
        for scenario_id in EXPECTED:
            if scenario_id not in existing:
                report["scenarios"].append({"id": scenario_id, "status": "INCOMPLETE",
                                            "reason": "harness aborted before scenario execution"})
    finally:
        # Two-phase emergency cleanup: stop every still-owned fixture first,
        # then remove only endpoints whose recorded identity can be revalidated.
        pending_cleanup = []
        if run_dir_fd is not None:
            for fixture_name, fixture in reversed(list(_ACTIVE_FIXTURES.items())):
                if fixture_name in _CLEANED_FIXTURES:
                    continue
                try:
                    initial_fixture = fixture["initial"]
                    if initial_fixture is None:
                        initial_fixture = unit_snapshot(fixture_name)
                        if (
                            initial_fixture["Id"] != fixture_name
                            or not initial_fixture["Transient"]
                            or initial_fixture["User"] != pwd.getpwuid(fixture["uid"]).pw_name
                            or initial_fixture["Group"] != grp.getgrgid(fixture["gid"]).gr_name
                        ):
                            raise Incomplete("cannot establish ownership of partially started fixture")
                        fixture["initial"] = initial_fixture
                    current_fixture = unit_snapshot(fixture_name)
                    if current_fixture["InvocationID"] != initial_fixture["InvocationID"]:
                        raise Incomplete("fixture InvocationID changed; emergency cleanup refuses replacement")
                    if current_fixture["ActiveState"] != "inactive" or current_fixture["Job"][0] != 0:
                        if current_fixture["Job"][0] == 0:
                            systemd_stop(fixture_name)
                        final_fixture = wait_inactive(
                            fixture_name, time.monotonic() + STOP_TIMEOUT + 5
                        )
                    else:
                        final_fixture = current_fixture
                    if final_fixture["ActiveState"] != "inactive" or final_fixture["Job"][0] != 0:
                        raise Incomplete("fixture did not reach inactive/no-job state during emergency cleanup")
                    _root, cleanup_mount = cgroup_mount()
                    events_fixture = cgroup_events(
                        cleanup_mount, initial_fixture["ControlGroup"]
                    )
                    if events_fixture["values"]["populated"] != 0:
                        raise Incomplete("fixture cgroup remains populated; preserving endpoint and gate")
                    pending_cleanup.append((fixture, initial_fixture))
                except Exception as exc:
                    report["cleanup"]["safe_to_release_gate"] = False
                    report["cleanup"].setdefault("emergency_errors", []).append(
                        {"unit": fixture_name, "error": f"{type(exc).__name__}: {exc}"}
                    )
            # Remove fixture pathnames only if every outstanding unit reached
            # inactive/no-job/populated=0; otherwise preserve all remaining objects.
            if report["cleanup"]["safe_to_release_gate"]:
                for fixture, initial_fixture in pending_cleanup:
                    try:
                        result = _stop_and_cleanup(
                            fixture["name"], initial_fixture, fixture["socket_path"],
                            fixture["ready_path"], fixture["dir_fd"], report,
                            already_stopped=True, cgroup_empty_confirmed=True,
                        )
                        report["cleanup"]["resources"].append(result)
                        if fixture["name"] not in _CLEANED_FIXTURES:
                            report["cleanup"]["safe_to_release_gate"] = False
                    except Exception as exc:
                        report["cleanup"]["safe_to_release_gate"] = False
                        report["cleanup"].setdefault("emergency_errors", []).append(
                            {"unit": fixture["name"], "error": f"{type(exc).__name__}: {exc}"}
                        )

        for directory_fd in set(_OPEN_DIR_FDS):
            try:
                os.close(directory_fd)
            except OSError:
                pass

        if report["cleanup"]["safe_to_release_gate"]:
            for entry in reversed(_SANDBOX_DIRS):
                try:
                    current = os.stat(entry["path"], follow_symlinks=False)
                    if (
                        not stat.S_ISDIR(current.st_mode)
                        or (current.st_dev, current.st_ino) != (entry["device"], entry["inode"])
                        or current.st_uid != entry["uid"] or current.st_gid != entry["gid"]
                        or stat.S_IMODE(current.st_mode) != entry["mode"]
                    ):
                        raise Incomplete("sandbox directory identity/mode changed; preserving it")
                    os.rmdir(entry["path"])
                except FileNotFoundError:
                    continue
                except Exception as exc:
                    report["cleanup"]["safe_to_release_gate"] = False
                    report["cleanup"].setdefault("directory_errors", []).append(
                        f"{entry['path']}: {type(exc).__name__}: {exc}"
                    )
                    break
        else:
            report["cleanup"]["sandbox_preserved_due_to_uncertainty"] = True

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
                validate_report_bounds(report)
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
                report["overall"] = (
                    "PASS" if len(statuses) == 15 and all(value == "PASS" for value in statuses)
                    and report["cleanup"]["safe_to_release_gate"]
                    else "FAIL" if "FAIL" in statuses or "harness_error" in report
                    else "INCOMPLETE"
                )
                _rewrite_json_file(report_path, report, MAX_REPORT)
            except Exception as exc:
                report["cleanup"]["safe_to_release_gate"] = False
                report["overall"] = "INCOMPLETE"
                report["gate"]["marker_removal_error"] = f"{type(exc).__name__}: {exc}"
                try:
                    if not marker.exists():
                        _safe_json_file(marker, {
                            "schema": SCHEMA, "run_id": run_id,
                            "phase": "report-finalization-failed",
                        }, 4096)
                        report["gate"]["marker_recreated_after_release_failure"] = True
                    _rewrite_json_file(report_path, report, MAX_REPORT)
                except Exception as recovery_exc:
                    report["gate"]["marker_recovery_error"] = (
                        f"{type(recovery_exc).__name__}: {recovery_exc}"
                    )
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
    parser.add_argument("--deny-fork", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--deny-fd-escape", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--exec-check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--exec-helper", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--listener-fd", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--original-pid", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--fd-holder", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--control", help=argparse.SUPPRESS)
    parser.add_argument("--received", help=argparse.SUPPRESS)
    parser.add_argument("--transfer-fd-to", help=argparse.SUPPRESS)
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
