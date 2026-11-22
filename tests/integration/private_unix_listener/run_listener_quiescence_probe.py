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
    result = subprocess.run(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout, check=False,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
    )
    if len(result.stdout) > limit or len(result.stderr) > limit:
        raise Incomplete(f"subprocess output exceeded {limit} bytes: {argv[0]}")
    if result.returncode:
        raise Incomplete(
            f"{argv[0]} exited {result.returncode}; "
            f"stderr={result.stderr[:512].decode('utf-8', 'replace')}"
        )
    return result.stdout


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
    }
    if values["Id"] != name or values["LoadState"] != "loaded":
        raise Incomplete("systemd returned a different or unloaded unit")
    if values["KillMode"] != "control-group" or values["Restart"] != "no":
        raise Incomplete("fixture unit lifecycle properties differ from contract")
    if not values["Transient"]:
        raise Incomplete("fixture unit is not transient")
    if not isinstance(values["InvocationID"], list) or len(values["InvocationID"]) != 16:
        raise Incomplete("InvocationID is not a 16-byte D-Bus ay")
    if not isinstance(values["Job"], list) or len(values["Job"]) != 2:
        raise Incomplete("Unit.Job has an unexpected D-Bus representation")
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


def systemd_stop(name: str) -> None:
    # The command only requests the transition; D-Bus/cgroup observations
    # below, not its human output, determine the result.
    bounded_run(["systemctl", "--no-block", "stop", name], timeout=5.0)


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
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        listener.set_inheritable(False)
        os.umask(0o177)
        listener.bind(args.socket)
        listener.listen(1)
        info = os.stat(args.socket, follow_symlinks=False)
        ready = {
            "pid": os.getpid(), "fd": listener.fileno(),
            "device": info.st_dev, "inode": info.st_ino,
            "uid": info.st_uid, "gid": info.st_gid,
            "mode": stat.S_IMODE(info.st_mode),
            "socket_type": listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE),
            "accepting": listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN),
            "cloexec": not os.get_inheritable(listener.fileno()),
        }
        fd = os.open(
            args.ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
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
    for executable in ("busctl", "systemd-run", "systemctl"):
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
    return {
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
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(errno.EIO, "short evidence write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _start_fixture(name: str, run_dir: Path, *, hold_child=False, ignore_term=False, delegate=False) -> tuple[dict, Path, Path]:
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
    bounded_run(command, timeout=8.0)
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
    info = os.stat(socket_path, follow_symlinks=False)
    if (
        not stat.S_ISSOCK(info.st_mode) or info.st_uid != SERVICE_UID
        or info.st_gid != SERVICE_GID or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_dev != ready["device"] or info.st_ino != ready["inode"]
    ):
        raise Incomplete("fixture endpoint identity/mode differs from readiness record")
    return snap, socket_path, ready_path


def _stop_and_cleanup(name: str, initial: dict, socket_path: Path | None, ready_path: Path | None,
                      run_dir_fd: int, report: dict) -> dict:
    cleanup = {"unit": name, "stop_requested": False, "unit_inactive": False,
               "cgroup_empty": False, "endpoint_removed": False}
    try:
        current = unit_snapshot(name)
        if current["InvocationID"] != initial["InvocationID"]:
            raise Incomplete("InvocationID changed before cleanup; refusing to stop replacement")
        systemd_stop(name)
        cleanup["stop_requested"] = True
        final = wait_inactive(name, time.monotonic() + STOP_TIMEOUT + 3)
        cleanup["unit_inactive"] = final["ActiveState"] == "inactive"
        root, mount = cgroup_mount()
        events = cgroup_events(mount, initial["ControlGroup"])
        cleanup["cgroup_empty"] = events["values"]["populated"] == 0
        if not cleanup["cgroup_empty"]:
            raise Incomplete("fixture cgroup remains populated during cleanup")
        if socket_path is not None:
            name_only = socket_path.name
            current_info = os.stat(name_only, dir_fd=run_dir_fd, follow_symlinks=False)
            if not stat.S_ISSOCK(current_info.st_mode) or current_info.st_uid != SERVICE_UID:
                raise Incomplete("fixture endpoint identity is not eligible for cleanup")
            if ready_path is not None:
                ready = json.loads(ready_path.read_text(encoding="ascii"))
                if (current_info.st_dev, current_info.st_ino) != (ready["device"], ready["inode"]):
                    raise Incomplete("fixture endpoint inode changed; preserving it")
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
    except Exception as exc:
        report["preflight"] = {"status": "INCOMPLETE", "reason": f"{type(exc).__name__}: {exc}"}
        report["overall"] = "INCOMPLETE"
        return report

    base_created = False
    run_dir = None
    run_dir_fd = None
    lock_fd = None
    marker = None
    try:
        try:
            os.mkdir(BASE, 0o711)
            base_created = True
            os.chown(BASE, 0, 0)
        except FileExistsError:
            info = os.stat(BASE, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o711:
                raise Incomplete("/run/atlas-qp exists with unexpected identity or mode")
        run_dir = BASE / run_id
        os.mkdir(run_dir, 0o730)
        os.chown(run_dir, 0, SERVICE_GID)
        os.chmod(run_dir, 0o730)
        run_dir_fd = os.open(run_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
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
        report["gate"] = {"flock_acquired": True, "sticky_marker_created": True,
                          "root_direct_bypass_protection": False}
        mount_root, mount = cgroup_mount()

        # QP-01: normal service-owned listener, full stop, two empty snapshots.
        name = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial, endpoint, ready_path = _start_fixture(name, run_dir)
        report["unit_identity"][name] = initial
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
        cleanup = _stop_and_cleanup(name, initial, endpoint, ready_path, run_dir_fd, report)
        report["cleanup"]["resources"].append(cleanup)
        report["scenarios"].append({"id": "QP-01", "status": "PASS",
                                    "decision": "QUIESCENT", "reason": "two stable empty-cgroup snapshots"})
        if not cleanup["endpoint_removed"] or not cleanup["cgroup_empty"]:
            raise Incomplete("QP-01 cleanup was not confirmed")

        # QP-02: child exists in the same service cgroup before listener creation.
        name2 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial2, endpoint2, ready2 = _start_fixture(name2, run_dir, hold_child=True)
        report["unit_identity"][name2] = initial2
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
        cleanup2 = _stop_and_cleanup(name2, initial2, endpoint2, ready2, run_dir_fd, report)
        report["cleanup"]["resources"].append(cleanup2)
        if not passed2 or not cleanup2["endpoint_removed"]:
            raise Incomplete("QP-02 failed its pre-stop helper or post-stop empty-cgroup check")
        report["scenarios"].append({"id": "QP-02", "status": "PASS",
                                    "decision": "QUIESCENT", "reason": "helper shared cgroup and terminated on stop"})

        # QP-06: Delegate=yes must be rejected; no cgroup writes or migration.
        name6 = f"atlas-qp-{secrets.token_hex(6)}.service"
        initial6, endpoint6, ready6 = _start_fixture(name6, run_dir, delegate=True)
        if initial6["Delegate"] is not True:
            raise Incomplete("QP-06 negative fixture did not expose Delegate=yes")
        cleanup6 = _stop_and_cleanup(name6, initial6, endpoint6, ready6, run_dir_fd, report)
        report["cleanup"]["resources"].append(cleanup6)
        if not cleanup6["unit_inactive"] or not cleanup6["cgroup_empty"] or not cleanup6["endpoint_removed"]:
            raise Incomplete("QP-06 negative fixture cleanup failed")
        report["scenarios"].append({"id": "QP-06", "status": "PASS",
                                    "decision": "ABORT_NOT_QUIESCENT",
                                    "reason": "Delegate=yes is rejected before quiescence"})

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
        report["scenarios"].append({"id": "QP-07", "status": "PASS",
                                    "reason": "strict parser accepts only complete known-key records",
                                    "observations": parser_results})

        implemented = {item["id"] for item in report["scenarios"]}
        reasons = {
            "QP-03": "pending: stop-deadline/TimeoutStopSec race harness",
            "QP-04": "pending: deterministic pending-job injection",
            "QP-05": "pending: dual-unit identity and adapter mismatch injection",
            "QP-08": "pending: libseccomp syscall-denial fixture",
            "QP-09": "pending: seccomp FD-duplication/SCM_RIGHTS denial fixture",
            "QP-10": "pending: same-process exec/CLOEXEC helper",
            "QP-11": "incomplete: no authorized lifecycle supervisor exists to exercise",
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
        # Do not remove a sticky marker or release the gate after an uncertain
        # cleanup. This intentionally leaves a manual-recovery condition.
        if report["cleanup"]["safe_to_release_gate"] and marker is not None:
            try:
                os.unlink(marker)
                report["gate"]["marker_removed_after_cleanup"] = True
            except FileNotFoundError:
                report["cleanup"]["safe_to_release_gate"] = False
        if lock_fd is not None:
            if report["cleanup"]["safe_to_release_gate"]:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if run_dir is not None and report["cleanup"]["safe_to_release_gate"]:
            try:
                os.rmdir(run_dir)
            except OSError as exc:
                report["cleanup"]["run_directory_preserved"] = f"errno={exc.errno}"
                report["cleanup"]["safe_to_release_gate"] = False
        if base_created and report["cleanup"]["safe_to_release_gate"]:
            try:
                os.unlink(BASE / "maintenance.lock")
                os.rmdir(BASE)
            except OSError:
                pass

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
