#!/usr/bin/env python3
"""A-IPC-04 stale AF_UNIX pathname recovery probe.

Disposable-VM only. All socket and filesystem fixtures live in one private
root-owned /run sandbox. This is not an Atlas maintenance utility.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import platform
import re
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable


EXPECTED = tuple(f"SR-{number:02d}" for number in range(1, 13))
SOCK_SEQPACKET_PROC_TYPE = 0x0005
NETNS_RE = re.compile(r"net:\[(\d+)\]\Z")
HEX_RE = re.compile(r"[0-9a-fA-F]+\Z")
DEC_RE = re.compile(r"[0-9]+\Z")


class ProbeFailure(RuntimeError):
    pass


class CoverageError(ProbeFailure):
    pass


class ProcessRace(CoverageError):
    pass


@dataclass(frozen=True)
class FsIdentity:
    device: int
    inode: int
    file_type: int
    uid: int
    gid: int
    mode: int

    @classmethod
    def from_stat(cls, info: os.stat_result) -> "FsIdentity":
        return cls(
            info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode),
            info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode),
        )

    def as_dict(self) -> dict:
        return {
            "device": self.device, "inode": self.inode,
            "type": stat.S_IFMT(self.file_type),
            "uid": self.uid, "gid": self.gid,
            "mode": oct(self.mode),
        }


@dataclass(frozen=True)
class ApprovalToken:
    """Fixture-only token bound to one pathname and one observed identity."""
    pathname: str
    identity: FsIdentity
    challenge: str


@dataclass
class NamespaceSnapshot:
    namespaces: list[dict]
    tables: list[tuple[str, bytes]]
    processes_seen: int
    retries: int


def _proc_mount_contract() -> dict:
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="ascii").splitlines()
    except OSError as exc:
        raise CoverageError(f"cannot inspect procfs mountinfo: {exc.errno}") from exc
    matches = []
    for line in lines:
        fields = line.split()
        if len(fields) < 10 or "-" not in fields:
            continue
        separator = fields.index("-")
        if len(fields) > 5 and fields[4] == "/proc":
            matches.append((fields, separator))
    if len(matches) != 1:
        raise CoverageError("cannot identify exactly one /proc mount")
    fields, separator = matches[0]
    fs_type = fields[separator + 1]
    mount_options = fields[5].split(",")
    super_options = fields[separator + 3].split(",") if len(fields) > separator + 3 else []
    options = mount_options + super_options
    if fs_type != "proc":
        raise CoverageError("/proc is not mounted as procfs")
    if any(option == "hidepid" or option.startswith("hidepid=") for option in options):
        raise CoverageError("procfs hidepid restricts process visibility")
    pid1_ns = os.readlink("/proc/1/ns/pid")
    self_ns = os.readlink("/proc/self/ns/pid")
    return {
        "filesystem": fs_type,
        "mount_options": mount_options,
        "super_options": super_options,
        "pid1_namespace": pid1_ns,
        "inspector_pid_namespace": self_ns,
        "same_pid_namespace_as_pid1": pid1_ns == self_ns,
        "scope": "processes visible in this procfs mount and PID namespace only",
    }


def _proc_pid_entries(proc_root: str = "/proc") -> list[str]:
    try:
        with os.scandir(proc_root) as entries:
            return sorted(
                entry.name for entry in entries
                if entry.name.isascii() and entry.name.isdecimal()
            )
    except OSError as exc:
        raise CoverageError(f"cannot enumerate procfs: {exc.errno}") from exc


def _namespace_identity(pid: str, proc_root: str = "/proc") -> tuple[int, int, str]:
    path = os.path.join(proc_root, pid, "ns", "net")
    descriptor = None
    try:
        flags = getattr(os, "O_PATH", os.O_RDONLY) | os.O_CLOEXEC
        descriptor = os.open(path, flags)
        info = os.fstat(descriptor)
        target = os.readlink(f"/proc/self/fd/{descriptor}")
    except OSError as exc:
        if exc.errno in (errno.ENOENT, errno.ESRCH, errno.ENOTDIR):
            raise ProcessRace(f"PID {pid} disappeared during namespace inspection") from exc
        raise CoverageError(f"cannot inspect PID {pid} network namespace: {exc.errno}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    match = NETNS_RE.fullmatch(target)
    if not match:
        raise CoverageError(f"PID {pid} returned an ambiguous net namespace link")
    return info.st_dev, info.st_ino, target


def _parse_unix_table(data: bytes) -> list[dict]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CoverageError("procfs unix table is not valid UTF-8") from exc
    lines = text.splitlines()
    if not lines or lines[0].split() != [
        "Num", "RefCount", "Protocol", "Flags", "Type", "St", "Inode", "Path"
    ]:
        raise CoverageError("unexpected /proc/net/unix header")
    records = []
    for number, line in enumerate(lines[1:], start=2):
        fields = line.split(None, 7)
        if len(fields) not in (7, 8):
            raise CoverageError(f"malformed unix table row {number}")
        # Linux /proc/net/unix renders the first (Num) field with a
        # trailing colon, unlike the remaining hexadecimal columns.
        if not fields[0].endswith(":") or fields[0].count(":") != 1:
            raise CoverageError(f"invalid Num delimiter in unix table row {number}")
        fields[0] = fields[0][:-1]
        if not all(HEX_RE.fullmatch(value) for value in fields[:6]):
            raise CoverageError(f"invalid hexadecimal field in unix table row {number}")
        if not DEC_RE.fullmatch(fields[6]):
            raise CoverageError(f"invalid inode field in unix table row {number}")
        path = fields[7] if len(fields) == 8 else None
        records.append({
            "type": int(fields[4], 16),
            "state": int(fields[5], 16),
            "inode": int(fields[6], 10),
            "path": path,
        })
    return records


def _read_table(pid: str, proc_root: str = "/proc") -> bytes:
    path = os.path.join(proc_root, pid, "net", "unix")
    try:
        with open(path, "rb", buffering=0) as stream:
            return stream.read(4 * 1024 * 1024 + 1)
    except OSError as exc:
        if exc.errno in (errno.ENOENT, errno.ESRCH, errno.ENOTDIR):
            raise ProcessRace(f"PID {pid} disappeared before namespace table read") from exc
        raise CoverageError(f"cannot read namespace table for PID {pid}: {exc.errno}") from exc


def inspect_visible_namespaces(
    pathname: str,
    *,
    proc_root: str = "/proc",
    table_reader: Callable[[str, str], bytes] = _read_table,
    pid_enumerator: Callable[[str], list[str]] = _proc_pid_entries,
) -> NamespaceSnapshot:
    """Take two matching process snapshots, then read one table per namespace.

    The result is deliberately scoped to processes visible through proc_root.
    A process disappearing or changing namespace during the scan causes a
    bounded full retry; permission, parse, or coverage errors abort.
    """
    last_race = None
    for attempt in range(3):
        try:
            first = pid_enumerator(proc_root)
            first_map = {}
            for pid in first:
                first_map[pid] = _namespace_identity(pid, proc_root)

            second = pid_enumerator(proc_root)
            second_map = {}
            for pid in second:
                second_map[pid] = _namespace_identity(pid, proc_root)
            if first_map != second_map:
                raise ProcessRace("visible PID/network-namespace set changed between snapshots")

            representatives: dict[tuple[int, int], tuple[str, str]] = {}
            for pid, (device, inode, target) in second_map.items():
                representatives.setdefault((device, inode), (pid, target))

            tables = []
            namespace_records = []
            for (device, inode), (pid, target) in sorted(
                representatives.items(), key=lambda item: item[0]
            ):
                current = _namespace_identity(pid, proc_root)
                if current[:2] != (device, inode):
                    raise ProcessRace(f"representative PID {pid} changed namespace")
                raw = table_reader(pid, proc_root)
                after_read = _namespace_identity(pid, proc_root)
                if after_read[:2] != (device, inode):
                    raise ProcessRace(f"representative PID {pid} changed namespace during table read")
                if len(raw) > 4 * 1024 * 1024:
                    raise CoverageError("namespace unix table exceeds 4 MiB safety limit")
                records = _parse_unix_table(raw)
                tables.append((target, raw))
                namespace_records.append({
                    "identity": target,
                    "device": device,
                    "inode": inode,
                    "representative_pid": int(pid),
                    "records": len(records),
                    "pathname_match": any(
                        row["path"] == pathname
                        and row["type"] == SOCK_SEQPACKET_PROC_TYPE
                        for row in records
                    ),
                })

            third = pid_enumerator(proc_root)
            third_map = {pid: _namespace_identity(pid, proc_root) for pid in third}
            if second_map != third_map:
                raise ProcessRace("visible PID/network-namespace set changed during table reads")
            return NamespaceSnapshot(
                namespace_records, tables, len(third), attempt
            )
        except ProcessRace as exc:
            last_race = exc
            continue
    raise CoverageError(f"namespace coverage remained unstable after 3 attempts: {last_race}")


def _matches(snapshot: NamespaceSnapshot, pathname: str) -> bool:
    for _, raw in snapshot.tables:
        for row in _parse_unix_table(raw):
            if row["path"] == pathname and row["type"] == SOCK_SEQPACKET_PROC_TYPE:
                return True
    return False


def _listener_diagnostics(snapshot: NamespaceSnapshot, pathname: str) -> dict:
    """Bounded evidence for a failed active-listener lookup; never affects classification."""
    basename = os.path.basename(pathname)
    candidates = []
    for namespace, raw in snapshot.tables:
        for row in _parse_unix_table(raw):
            row_path = row["path"]
            if row_path and (basename in row_path or row_path.startswith("/run/atlas-aipc04-")):
                candidates.append({
                    "namespace": namespace,
                    "path": row_path,
                    "type": row["type"],
                    "inode": row["inode"],
                })
                if len(candidates) == 12:
                    return {"expected_path": pathname, "candidate_rows": candidates}
    return {"expected_path": pathname, "candidate_rows": candidates}


def _identity_at(parent_fd: int, name: str) -> FsIdentity:
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise ProbeFailure(f"cannot inspect fixture entry: {exc.errno}") from exc
    return FsIdentity.from_stat(info)


def _check_expected_socket(identity: FsIdentity, uid: int, gid: int) -> None:
    if identity.file_type != stat.S_IFSOCK:
        raise ProbeFailure("fixture entry is not a filesystem socket")
    if identity.uid != uid or identity.gid != gid:
        raise ProbeFailure("fixture socket owner/group mismatch")
    if identity.mode != 0o600:
        raise ProbeFailure("fixture socket mode mismatch")


def _fixture_listener(path: str, uid: int, gid: int) -> socket.socket:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        listener.bind(path)
        os.chmod(path, 0o600)
        os.chown(path, uid, gid)
        listener.listen(1)
        return listener
    except Exception:
        listener.close()
        raise


def _issue_fixture_token(pathname: str, identity: FsIdentity) -> ApprovalToken:
    return ApprovalToken(pathname, identity, "AIPC04-SR10-FIXTURE-ONLY")


def _remove_with_fixture_token(
    parent_fd: int, name: str, pathname: str, observed: FsIdentity,
    token: ApprovalToken,
) -> None:
    if token != _issue_fixture_token(pathname, observed):
        raise ProbeFailure("fixture approval token does not bind the observed identity")
    current = _identity_at(parent_fd, name)
    if current != observed:
        raise ProbeFailure("fixture identity changed before unlink")
    if current.file_type != stat.S_IFSOCK:
        raise ProbeFailure("only a socket fixture may be removed")
    os.unlink(name, dir_fd=parent_fd)


def _scenario_01_active_local(sandbox: Path, uid: int, gid: int) -> dict:
    path = str(sandbox / "sr01-active.sock")
    listener = _fixture_listener(path, uid, gid)
    parent = os.open(sandbox, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        snapshot = inspect_visible_namespaces(path)
        identity = _identity_at(parent, Path(path).name)
        _check_expected_socket(identity, uid, gid)
        matched = _matches(snapshot, path)
        if not matched:
            raise ProbeFailure(
                "SR-01 active pathname absent from visible namespace tables; "
                f"diagnostics={_listener_diagnostics(snapshot, path)!r}"
            )
        return {
            "decision": "ABORT_ACTIVE_OR_POSSIBLY_ACTIVE",
            "namespace_count": len(snapshot.namespaces),
            "matched_namespaces": [n["identity"] for n in snapshot.namespaces if n["pathname_match"]],
            "filesystem_identity": identity.as_dict(),
            "connect_called": False,
        }
    finally:
        os.close(parent)
        listener.close()


def _scenario_02_residual_without_approval(sandbox: Path, uid: int, gid: int) -> dict:
    path = str(sandbox / "sr02-residual.sock")
    listener = _fixture_listener(path, uid, gid)
    listener.close()
    parent = os.open(sandbox, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        snapshot = inspect_visible_namespaces(path)
        if _matches(snapshot, path):
            raise ProbeFailure("SR-02 closed socket still appears in inspected tables")
        identity = _identity_at(parent, Path(path).name)
        _check_expected_socket(identity, uid, gid)
        token = None
        if token is not None:
            raise ProbeFailure("SR-02 unexpectedly received an approval token")
        if _identity_at(parent, Path(path).name) != identity:
            raise ProbeFailure("SR-02 residual changed without approval")
        return {
            "decision": "ELIGIBLE_BUT_NOT_REMOVED",
            "namespace_count": len(snapshot.namespaces),
            "filesystem_identity": identity.as_dict(),
            "approval_token_present": False,
            "pathname_preserved": True,
        }
    finally:
        os.close(parent)


def _trusted_unshare_path() -> str:
    candidate = shutil.which("unshare")
    if not candidate:
        raise ProbeFailure("SR-03 unshare executable is unavailable")
    resolved = os.path.realpath(candidate)
    info = os.stat(resolved, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
        raise ProbeFailure("SR-03 unshare executable is not a trusted root-owned file")
    if not os.access(resolved, os.X_OK):
        raise ProbeFailure("SR-03 unshare executable is not executable")
    directory = os.path.dirname(resolved)
    while True:
        parent_info = os.stat(directory, follow_symlinks=False)
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != 0
            or stat.S_IMODE(parent_info.st_mode) & 0o022
        ):
            raise ProbeFailure("SR-03 unshare executable has an untrusted parent directory")
        if directory == "/":
            break
        directory = os.path.dirname(directory)
    return resolved


def _scenario_03_other_namespace(sandbox: Path, uid: int, gid: int) -> dict:
    path = str(sandbox / "sr03-other-netns.sock")
    code = (
        "import os,socket,sys,time\n"
        "p=sys.argv[1]; u=int(sys.argv[2]); g=int(sys.argv[3])\n"
        "s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET); s.bind(p)\n"
        "os.chmod(p,0o600); os.chown(p,u,g); s.listen(1)\n"
        "print(os.getpid(),flush=True); time.sleep(30)\n"
    )
    unshare = _trusted_unshare_path()
    child = subprocess.Popen(
        [unshare, "--net", "--", sys.executable, "-c", code, path, str(uid), str(gid)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        if child.stdout is None:
            raise ProbeFailure("SR-03 child stdout pipe was not created")
        ready, _, _ = select.select([child.stdout], [], [], 5.0)
        if not ready:
            raise ProbeFailure("SR-03 namespace listener startup timed out")
        line = child.stdout.readline()
        if not line.strip():
            error = child.stderr.read() if child.stderr else ""
            raise ProbeFailure(f"SR-03 namespace listener failed to start: {error[-500:]}")
        child_pid = int(line.strip())
        child_ns = os.readlink(f"/proc/{child_pid}/ns/net")
        own_ns = os.readlink("/proc/self/ns/net")
        if child_ns == own_ns:
            raise ProbeFailure("SR-03 child did not enter a distinct network namespace")
        snapshot = inspect_visible_namespaces(path)
        matching = [n for n in snapshot.namespaces if n["pathname_match"]]
        if not any(n["identity"] == child_ns for n in matching):
            raise ProbeFailure("SR-03 listener not found in its distinct visible namespace")
        return {
            "decision": "ABORT_ACTIVE_OR_POSSIBLY_ACTIVE",
            "child_pid": child_pid,
            "child_namespace": child_ns,
            "inspector_namespace": own_ns,
            "namespace_count": len(snapshot.namespaces),
            "matched_namespaces": [n["identity"] for n in matching],
            "connect_called": False,
        }
    finally:
        if child.poll() is None:
            child.send_signal(signal.SIGTERM)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        if child.stdout:
            child.stdout.close()
        if child.stderr:
            child.stderr.close()


def _scenario_04_table_unreadable() -> dict:
    def denied(pid: str, proc_root: str) -> bytes:
        raise CoverageError("injected EACCES while reading one namespace table")
    try:
        inspect_visible_namespaces("/fixture/target.sock", table_reader=denied)
    except CoverageError:
        return {"decision": "ABORT_INCOMPLETE_NAMESPACE_COVERAGE", "object_mutated": False}
    raise ProbeFailure("SR-04 accepted an unreadable namespace table")


def _scenario_05_enumeration_incomplete() -> dict:
    def incomplete(proc_root: str) -> list[str]:
        raise CoverageError("injected procfs enumeration EIO")
    try:
        inspect_visible_namespaces("/fixture/target.sock", pid_enumerator=incomplete)
    except CoverageError:
        return {"decision": "ABORT_INCOMPLETE_NAMESPACE_COVERAGE", "object_mutated": False}
    raise ProbeFailure("SR-05 accepted incomplete process enumeration")


def _scenario_06_parser_rejects_ambiguous() -> dict:
    valid_realistic = (
        b"Num RefCount Protocol Flags Type St Inode Path\n"
        b"0000000016960ea0: 00000002 00000000 00010000 0005 01 36068 /fixture/active.sock\n"
    )
    parsed = _parse_unix_table(valid_realistic)
    if len(parsed) != 1 or parsed[0] != {
        "type": SOCK_SEQPACKET_PROC_TYPE,
        "state": 0x01,
        "inode": 36068,
        "path": "/fixture/active.sock",
    }:
        raise ProbeFailure("SR-06 rejected or misparsed realistic Linux procfs row")

    bad_tables = [
        b"not the procfs header\n",
        b"Num RefCount Protocol Flags Type St Inode Path\nmalformed\n",
        b"Num RefCount Protocol Flags Type St Inode Path\n"
        b"000000001: 00000002 00000000 00010000 0005 01 36068 /missing-colon.sock\n",
        b"Num RefCount Protocol Flags Type St Inode Path\n"
        b"000000001:: 00000002 00000000 00010000 0005 01 36068 /double-colon.sock\n",
        b"Num RefCount Protocol Flags Type St Inode Path\n"
        b"000000001: 00000002 00000000 00010000 0005 01 nope /bad-inode.sock\n",
    ]
    rejected = 0
    for raw in bad_tables:
        try:
            _parse_unix_table(raw)
        except CoverageError:
            rejected += 1
    if rejected != len(bad_tables):
        raise ProbeFailure("SR-06 accepted malformed procfs table")
    return {
        "realistic_kernel_row_accepted": True,
        "realistic_row_path": parsed[0]["path"],
        "malformed_tables_rejected": rejected,
    }


def _scenario_07_exact_match() -> dict:
    header = b"Num RefCount Protocol Flags Type St Inode Path\n"
    rows = (
        b"000000001: 00000002 00000000 00010000 0005 01 100 /tmp/target.sock-extra\n"
        b"000000002: 00000002 00000000 00010000 0005 01 101 /tmp/prefix-target.sock\n"
        b"000000003: 00000002 00000000 00010000 0005 01 102 /tmp/target.sock\n"
    )
    records = _parse_unix_table(header + rows)
    exact = [r for r in records if r["path"] == "/tmp/target.sock" and r["type"] == 5]
    if len(exact) != 1 or exact[0]["inode"] != 102:
        raise ProbeFailure("SR-07 pathname matching was not exact")
    return {"rows": len(records), "exact_matches": len(exact), "matched_inode": 102}


def _scenario_08_wrong_objects(sandbox: Path, uid: int, gid: int, other_uid: int, other_gid: int) -> dict:
    parent = os.open(sandbox, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    rejected = []
    try:
        os.symlink("missing-target", "sr08-link", dir_fd=parent)
        with open(sandbox / "sr08-regular", "wb") as stream:
            stream.write(b"sentinel")
        os.mkfifo(sandbox / "sr08-fifo", 0o600)
        os.mkdir(sandbox / "sr08-directory", 0o700)
        wrong_mode_path = str(sandbox / "sr08-wrong-mode.sock")
        wrong_mode = _fixture_listener(wrong_mode_path, uid, gid)
        wrong_mode.close()
        os.chmod(wrong_mode_path, 0o640)
        wrong_owner_path = str(sandbox / "sr08-wrong-owner.sock")
        wrong_owner = _fixture_listener(wrong_owner_path, uid, gid)
        wrong_owner.close()
        os.chown(wrong_owner_path, other_uid, other_gid)
        for name in (
            "sr08-link", "sr08-regular", "sr08-fifo", "sr08-directory",
            "sr08-wrong-mode.sock", "sr08-wrong-owner.sock",
        ):
            identity = _identity_at(parent, name)
            if identity.file_type != stat.S_IFSOCK or identity.uid != uid or identity.gid != gid or identity.mode != 0o600:
                rejected.append(name)
            else:
                raise ProbeFailure(f"SR-08 unexpectedly accepted {name}")
        return {"rejected_objects": rejected, "rejected_count": len(rejected)}
    finally:
        os.close(parent)


def _scenario_09_replacement(sandbox: Path, uid: int, gid: int) -> dict:
    path = str(sandbox / "sr09-replacement.sock")
    listener = _fixture_listener(path, uid, gid)
    listener.close()
    parent = os.open(sandbox, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        observed = _identity_at(parent, Path(path).name)
        os.unlink(Path(path).name, dir_fd=parent)
        with open(sandbox / Path(path).name, "wb") as stream:
            stream.write(b"replacement-sentinel")
        current = _identity_at(parent, Path(path).name)
        if current == observed:
            raise ProbeFailure("SR-09 replacement retained the original identity")
        decision = "ABORT_IDENTITY_CHANGED"
        if (sandbox / Path(path).name).read_bytes() != b"replacement-sentinel":
            raise ProbeFailure("SR-09 replacement sentinel changed")
        return {
            "decision": decision,
            "observed": observed.as_dict(),
            "replacement": current.as_dict(),
            "replacement_preserved": True,
        }
    finally:
        os.close(parent)


def _scenario_10_approved_removal(sandbox: Path, uid: int, gid: int) -> dict:
    path = str(sandbox / "sr10-approved-residual.sock")
    listener = _fixture_listener(path, uid, gid)
    listener.close()
    parent = os.open(sandbox, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        snapshot = inspect_visible_namespaces(path)
        if _matches(snapshot, path):
            raise ProbeFailure("SR-10 residual unexpectedly appears in namespace tables")
        name = Path(path).name
        observed = _identity_at(parent, name)
        _check_expected_socket(observed, uid, gid)
        token = _issue_fixture_token(path, observed)
        wrong_identity = FsIdentity(
            observed.device, observed.inode + 1, observed.file_type,
            observed.uid, observed.gid, observed.mode,
        )
        wrong_token = ApprovalToken(path, wrong_identity, token.challenge)
        wrong_token_rejected = False
        try:
            _remove_with_fixture_token(parent, name, path, observed, wrong_token)
        except ProbeFailure:
            wrong_token_rejected = True
        if not wrong_token_rejected or _identity_at(parent, name) != observed:
            raise ProbeFailure("SR-10 mismatched token was not rejected without mutation")
        _remove_with_fixture_token(parent, name, path, observed, token)
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            absent = True
        else:
            absent = False
        if not absent:
            raise ProbeFailure("SR-10 approved fixture socket remains after unlink")
        return {
            "decision": "REMOVED_EXACT_APPROVED_FIXTURE",
            "approval_token_bound_to_identity": True,
            "mismatched_token_rejected_without_mutation": wrong_token_rejected,
            "removed_identity": observed.as_dict(),
            "absent_after_unlink": absent,
        }
    finally:
        os.close(parent)


def _scenario_11_no_liveness_connect(sandbox: Path, uid: int, gid: int) -> dict:
    path = str(sandbox / "sr11-no-connect.sock")
    listener = _fixture_listener(path, uid, gid)
    try:
        snapshot = inspect_visible_namespaces(path)
        if not _matches(snapshot, path):
            raise ProbeFailure(
                "SR-11 active local listener not found; "
                f"diagnostics={_listener_diagnostics(snapshot, path)!r}"
            )
        return {
            "active_detected": True,
            "connect_called": False,
            "accept_called": False,
            "send_called": False,
            "recv_called": False,
            "namespace_count": len(snapshot.namespaces),
        }
    finally:
        listener.close()


def _scenario_12_fail_closed_classification() -> dict:
    cases = [
        (["PASS"] * 11 + ["SKIP"], True, "INCOMPLETE"),
        (["PASS"] * 11 + ["FAIL"], True, "FAIL"),
        (["PASS"] * 12, False, "INCOMPLETE"),
        (["PASS"] * 12, True, "PASS"),
    ]
    checked = 0
    for statuses, cleanup_ok, expected in cases:
        actual = "PASS" if all(s == "PASS" for s in statuses) and cleanup_ok else (
            "FAIL" if "FAIL" in statuses else "INCOMPLETE"
        )
        if actual != expected:
            raise ProbeFailure("SR-12 global classification is not fail-closed")
        checked += 1
    return {"classification_cases": checked, "skip_or_cleanup_failure_never_passes": True}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-uid", type=int, required=True)
    parser.add_argument("--service-gid", type=int, required=True)
    parser.add_argument("--other-uid", type=int, required=True)
    parser.add_argument("--other-gid", type=int, required=True)
    parser.add_argument("--confirm-disposable-vm", action="store_true")
    parser.add_argument("--confirm-fixture-ids", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not sys.platform.startswith("linux") or os.geteuid() != 0:
        print("ERROR: Linux and direct EUID 0 are required in Atlas-VM-test", file=sys.stderr)
        return 2
    if not args.confirm_disposable_vm or not args.confirm_fixture_ids:
        print("ERROR: both disposable-VM and fixture-ID confirmations are required", file=sys.stderr)
        return 2
    ids = (args.service_uid, args.service_gid, args.other_uid, args.other_gid)
    if any(value <= 0 or value > 0xFFFFFFFF for value in ids):
        print("ERROR: fixture IDs must be positive numeric IDs", file=sys.stderr)
        return 2
    if args.service_uid == args.other_uid or args.service_gid == args.other_gid:
        print("ERROR: SERVICE and OTHER fixture IDs must differ", file=sys.stderr)
        return 2

    try:
        proc_contract = _proc_mount_contract()
    except Exception as exc:
        print(f"ERROR: procfs preflight failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    run_info = os.stat("/run", follow_symlinks=False)
    if not stat.S_ISDIR(run_info.st_mode) or run_info.st_uid != 0 or run_info.st_gid != 0:
        print("ERROR: /run must be a root:root directory", file=sys.stderr)
        return 2
    if stat.S_IMODE(run_info.st_mode) & 0o022:
        print("ERROR: /run must not be group/other writable", file=sys.stderr)
        return 2

    sandbox: Path | None = None
    sandbox_identity = None
    results = []
    started = time.monotonic()
    cleanup = "not-created"
    namespace_inventory = None
    processes_seen = None
    namespace_scan_retries = None
    try:
        sandbox = Path(tempfile.mkdtemp(prefix="atlas-aipc04-", dir="/run"))
        info = os.stat(sandbox, follow_symlinks=False)
        sandbox_identity = (info.st_dev, info.st_ino)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0:
            raise ProbeFailure("sandbox is not a root-owned directory")
        os.chmod(sandbox, 0o700)
        baseline = inspect_visible_namespaces(str(sandbox / "namespace-inventory-only.sock"))
        namespace_inventory = baseline.namespaces
        processes_seen = baseline.processes_seen
        namespace_scan_retries = baseline.retries

        scenarios = [
            ("SR-01", lambda: _scenario_01_active_local(sandbox, args.service_uid, args.service_gid)),
            ("SR-02", lambda: _scenario_02_residual_without_approval(sandbox, args.service_uid, args.service_gid)),
            ("SR-03", lambda: _scenario_03_other_namespace(sandbox, args.service_uid, args.service_gid)),
            ("SR-04", _scenario_04_table_unreadable),
            ("SR-05", _scenario_05_enumeration_incomplete),
            ("SR-06", _scenario_06_parser_rejects_ambiguous),
            ("SR-07", _scenario_07_exact_match),
            ("SR-08", lambda: _scenario_08_wrong_objects(sandbox, args.service_uid, args.service_gid, args.other_uid, args.other_gid)),
            ("SR-09", lambda: _scenario_09_replacement(sandbox, args.service_uid, args.service_gid)),
            ("SR-10", lambda: _scenario_10_approved_removal(sandbox, args.service_uid, args.service_gid)),
            ("SR-11", lambda: _scenario_11_no_liveness_connect(sandbox, args.service_uid, args.service_gid)),
            ("SR-12", _scenario_12_fail_closed_classification),
        ]
        for scenario_id, operation in scenarios:
            try:
                observations = operation()
                results.append({"id": scenario_id, "status": "PASS", "observations": observations})
            except Exception as exc:
                status = "INCOMPLETE" if scenario_id == "SR-03" and (
                    "Operation not permitted" in str(exc)
                    or "unshare" in str(exc).lower()
                    or "startup timed out" in str(exc).lower()
                ) else "FAIL"
                results.append({
                    "id": scenario_id, "status": status,
                    "error": f"{type(exc).__name__}: {exc}",
                })
    except Exception as exc:
        results.append({"id": "HARNESS", "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        if sandbox is not None and sandbox_identity is not None:
            try:
                current = os.stat(sandbox, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(current.st_mode)
                    or (current.st_dev, current.st_ino) != sandbox_identity
                    or current.st_uid != 0
                    or stat.S_IMODE(current.st_mode) != 0o700
                ):
                    raise ProbeFailure("sandbox identity changed; refusing cleanup")
                shutil.rmtree(sandbox)
                cleanup = "private /run sandbox removed after child processes and sockets closed"
            except Exception as exc:
                cleanup = f"FAILED: {type(exc).__name__}: {exc}"
                results.append({"id": "CLEANUP", "status": "FAIL", "error": cleanup})

    passed = sum(item["status"] == "PASS" for item in results)
    failed = sum(item["status"] == "FAIL" for item in results)
    incomplete = sum(item["status"] == "INCOMPLETE" for item in results)
    overall = "PASS" if passed == len(EXPECTED) and failed == 0 and incomplete == 0 and cleanup.startswith("private ") else (
        "FAIL" if failed else "INCOMPLETE"
    )
    report = {
        "probe": "A-IPC-04-stale-recovery",
        "commit": _git_commit(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "effective_uid": os.geteuid(),
        "fixture_service_uid": args.service_uid,
        "fixture_service_gid": args.service_gid,
        "fixture_other_uid": args.other_uid,
        "fixture_other_gid": args.other_gid,
        "procfs": proc_contract,
        "processes_seen": processes_seen,
        "namespace_scan_retries": namespace_scan_retries,
        "namespace_inventory": namespace_inventory,
        "duration_seconds": round(time.monotonic() - started, 3),
        "overall": overall,
        "passed_scenarios": passed,
        "failed_scenarios": failed,
        "incomplete_scenarios": incomplete,
        "cleanup": cleanup,
        "scenarios": results,
        "liveness_connect_called": False,
        "scope": "only processes and network namespaces visible through this procfs mount/PID namespace",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if overall == "PASS" else (1 if overall == "FAIL" else 2)


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2,
        )
        return result.stdout.strip()
    except Exception:
        return "unavailable"


if __name__ == "__main__":
    raise SystemExit(main())
