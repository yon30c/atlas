#!/usr/bin/env python3
"""Root-only disposable-VM probe for A-THREAT-06 path resolution.

This is experimental harness code, not a production Atlas path API.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from probe_config import ProbeConfigRejected, load_probe_config_at


DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
SAFE_COMPONENT = re.compile(r"[A-Za-z0-9_.-]+\Z")
EXPECTED_SCENARIOS = tuple(f"PR-{number:02d}" for number in range(1, 13))

def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None



class ProbeFailure(RuntimeError):
    """An expected path-resolution invariant was not demonstrated."""


class PathRejected(ProbeFailure):
    """A path failed the closed path-walk contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def _components(path: str) -> tuple[str, ...]:
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        raise PathRejected("path must be absolute and must not begin with //")
    if "\x00" in path or not path.isascii():
        raise PathRejected("path must be NUL-free ASCII")
    if path == "/":
        return ()
    if path.endswith("/"):
        raise PathRejected("trailing separator is not canonical")
    parts = path[1:].split("/")
    if any(not part or part in {".", ".."} or not SAFE_COMPONENT.fullmatch(part) for part in parts):
        raise PathRejected("path contains an empty, dot, dot-dot, or unsupported component")
    return tuple(parts)


def _metadata(info: os.stat_result) -> dict:
    return {
        "type": (
            "directory" if stat.S_ISDIR(info.st_mode)
            else "regular" if stat.S_ISREG(info.st_mode)
            else "symlink" if stat.S_ISLNK(info.st_mode)
            else "other"
        ),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": oct(stat.S_IMODE(info.st_mode)),
        "device": info.st_dev,
        "inode": info.st_ino,
    }


def _validate_root_fd(fd: int) -> dict:
    info = os.fstat(fd)
    require(stat.S_ISDIR(info.st_mode), "root descriptor is not a directory")
    require(info.st_uid == 0 and info.st_gid == 0, "root descriptor is not root:root")
    require((stat.S_IMODE(info.st_mode) & 0o022) == 0, "root descriptor is writable by group/other")
    return _metadata(info)


def open_directory_path(
    path: str,
    *,
    endpoint_identity: tuple[int, int] | None = None,
) -> tuple[int, list[dict]]:
    """Walk from / with descriptor-relative O_DIRECTORY|O_NOFOLLOW opens."""
    parts = _components(path)
    current_fd = os.open("/", DIRECTORY_FLAGS)
    records: list[dict] = []
    try:
        records.append({"component": "/", **_validate_root_fd(current_fd)})
        if not parts:
            return current_fd, records
        for index, component in enumerate(parts):
            next_fd = os.open(component, DIRECTORY_FLAGS, dir_fd=current_fd)
            info = os.fstat(next_fd)
            if not stat.S_ISDIR(info.st_mode):
                os.close(next_fd)
                raise PathRejected(f"component {component!r} is not a directory")
            final = index == len(parts) - 1
            mode = stat.S_IMODE(info.st_mode)
            if final and endpoint_identity is not None:
                expected_uid, expected_gid = endpoint_identity
                if (info.st_uid, info.st_gid, mode) != (expected_uid, expected_gid, 0o700):
                    os.close(next_fd)
                    raise PathRejected(
                        f"endpoint directory identity/mode mismatch at {component!r}"
                    )
            else:
                if info.st_uid != 0 or info.st_gid != 0:
                    os.close(next_fd)
                    raise PathRejected(f"ancestor {component!r} is not root:root")
                if mode & 0o022:
                    os.close(next_fd)
                    raise PathRejected(f"ancestor {component!r} is writable by group/other")
            records.append({"component": component, **_metadata(info)})
            os.close(current_fd)
            current_fd = next_fd
        return current_fd, records
    except Exception:
        try:
            os.close(current_fd)
        except OSError:
            pass
        raise


def _mkdir(path: Path, *, uid: int = 0, gid: int = 0, mode: int = 0o700) -> None:
    path.mkdir(mode=mode)
    os.chown(path, uid, gid, follow_symlinks=False)
    os.chmod(path, mode)


def _write_file(path: Path, data: bytes, *, uid: int = 0, gid: int = 0, mode: int = 0o644) -> None:
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        mode,
    )
    try:
        os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise ProbeFailure("short fixture write")
            view = view[count:]
    finally:
        os.close(fd)


def _config_bytes(service_uid: int, service_gid: int) -> bytes:
    return (
        "schema_version=1\n"
        f"service_uid={service_uid}\n"
        f"service_gid={service_gid}\n"
        "client_uids=0\n"
        "socket_path=/run/atlas/admin.sock\n"
        "socket_type=SOCK_SEQPACKET\n"
        "socket_mode=0600\n"
        "socket_dir_mode=0700\n"
    ).encode("ascii")


def _expect_path_rejected(path: str, **kwargs) -> None:
    try:
        fd, _ = open_directory_path(path, **kwargs)
    except (PathRejected, OSError, ValueError):
        return
    else:
        os.close(fd)
        raise ProbeFailure(f"unsafe path unexpectedly accepted: {path!r}")


def _scenario_01_lexical_rejection() -> dict:
    invalid = [
        "relative/path",
        "//run/atlas",
        "/run//atlas",
        "/run/atlas/",
        "/run/./atlas",
        "/run/../atlas",
        "/run/atlas\x00/socket",
        "/run/atlas with-space",
        "/run/atlas/ümlaut",
    ]
    rejected = 0
    for path in invalid:
        try:
            _components(path)
        except PathRejected:
            rejected += 1
        else:
            raise ProbeFailure(f"PR-01 accepted non-canonical path {path!r}")
    return {"rejected_count": rejected, "cases": len(invalid)}


def _scenario_02_valid_walk(root: Path) -> dict:
    target = root / "etc" / "atlas"
    _mkdir(root / "etc")
    _mkdir(target)
    fd, records = open_directory_path(str(target))
    try:
        actual = os.fstat(fd)
        expected = os.stat(target, follow_symlinks=False)
        require((actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino),
                "PR-02 final descriptor does not match expected directory inode")
        require(len(records) >= 5, "PR-02 did not record every traversed component")
        return {"components_recorded": len(records), "final": _metadata(actual)}
    finally:
        os.close(fd)


def _scenario_03_symlink_ancestors(sandbox: Path) -> dict:
    outside = sandbox / "outside-target"
    _mkdir(outside)
    _mkdir(outside / "beta")
    _mkdir(outside / "beta" / "gamma")
    _mkdir(outside / "gamma")
    sentinel = outside / "sentinel"
    _write_file(sentinel, b"untouched")
    levels = ("alpha", "beta", "gamma")
    rejected = []
    for index, level in enumerate(levels):
        case_root = sandbox / f"symlink-case-{index}"
        _mkdir(case_root)
        for parent_level in levels[:index]:
            _mkdir(case_root / parent_level)
        link_path = case_root / level
        os.symlink(outside, link_path)
        remaining = levels[index + 1 :]
        candidate = link_path.joinpath(*remaining)
        try:
            _expect_path_rejected(str(candidate))
        except Exception:
            raise
        rejected.append(level)
    require(sentinel.read_bytes() == b"untouched", "PR-03 symlink target sentinel changed")
    return {"rejected_levels": rejected, "sentinel_unchanged": True}


def _scenario_04_non_directory(sandbox: Path) -> dict:
    parent = sandbox / "regular-component"
    _mkdir(parent)
    file_path = parent / "not-a-directory"
    _write_file(file_path, b"not a directory")
    _expect_path_rejected(str(file_path / "child"))
    return {"regular_component_rejected": True}


def _scenario_05_writable_ancestors(sandbox: Path) -> dict:
    cases = (("group-writable", 0o770), ("other-writable", 0o777))
    rejected = []
    for name, mode in cases:
        path = sandbox / name
        _mkdir(path, mode=mode)
        _mkdir(path / "child")
        _expect_path_rejected(str(path / "child"))
        rejected.append(name)
    return {"rejected": rejected}


def _scenario_06_wrong_owner(sandbox: Path, other_uid: int, other_gid: int) -> dict:
    path = sandbox / "other-owned-ancestor"
    _mkdir(path, uid=other_uid, gid=other_gid, mode=0o700)
    _mkdir(path / "child")
    _expect_path_rejected(str(path / "child"))
    return {"other_uid": other_uid, "other_gid": other_gid, "rejected": True}


def _scenario_07_endpoint_owner(
    sandbox: Path, service_uid: int, service_gid: int
) -> dict:
    path = sandbox / "endpoint-valid"
    _mkdir(path)
    endpoint = path / "service"
    _mkdir(endpoint, uid=service_uid, gid=service_gid, mode=0o700)
    fd, records = open_directory_path(
        str(endpoint), endpoint_identity=(service_uid, service_gid)
    )
    try:
        info = os.fstat(fd)
        require(info.st_uid == service_uid and info.st_gid == service_gid,
                "PR-07 endpoint UID/GID mismatch")
        require(stat.S_IMODE(info.st_mode) == 0o700, "PR-07 endpoint mode mismatch")
        return {"endpoint": _metadata(info), "components_recorded": len(records)}
    finally:
        os.close(fd)


def _scenario_08_endpoint_rejection(
    sandbox: Path, service_uid: int, service_gid: int, other_uid: int, other_gid: int
) -> dict:
    wrong_owner_parent = sandbox / "endpoint-wrong-owner-parent"
    _mkdir(wrong_owner_parent)
    wrong_owner = wrong_owner_parent / "endpoint"
    _mkdir(wrong_owner, uid=other_uid, gid=other_gid, mode=0o700)
    _expect_path_rejected(
        str(wrong_owner), endpoint_identity=(service_uid, service_gid)
    )

    wrong_mode_parent = sandbox / "endpoint-wrong-mode-parent"
    _mkdir(wrong_mode_parent)
    wrong_mode = wrong_mode_parent / "endpoint"
    _mkdir(wrong_mode, uid=service_uid, gid=service_gid, mode=0o750)
    _expect_path_rejected(
        str(wrong_mode), endpoint_identity=(service_uid, service_gid)
    )
    return {"wrong_owner_rejected": True, "wrong_mode_rejected": True}


def _scenario_09_config_via_parent_fd(
    sandbox: Path, service_uid: int, service_gid: int
) -> dict:
    config_dir = sandbox / "config-root" / "etc" / "atlas"
    _mkdir(sandbox / "config-root")
    _mkdir(config_dir.parent)
    _mkdir(config_dir)
    config_path = config_dir / "admin-ipc.conf"
    _write_file(config_path, _config_bytes(service_uid, service_gid))
    parent_fd, records = open_directory_path(str(config_dir))
    try:
        snapshot = load_probe_config_at(
            parent_fd,
            "admin-ipc.conf",
            expected_service_uid=service_uid,
            expected_service_gid=service_gid,
        )
        require(snapshot.service_uid == service_uid, "PR-09 service UID mismatch")
        require(snapshot.service_gid == service_gid, "PR-09 service GID mismatch")
        require(snapshot.client_uids == (0,), "PR-09 client UID allowlist mismatch")
        return {
            "snapshot_loaded": True,
            "service_uid": snapshot.service_uid,
            "service_gid": snapshot.service_gid,
            "client_uids": list(snapshot.client_uids),
            "components_recorded": len(records),
        }
    finally:
        os.close(parent_fd)


def _scenario_10_config_final_objects(
    sandbox: Path, service_uid: int, service_gid: int
) -> dict:
    from probe_config import load_probe_config_at

    directory = sandbox / "config-final-objects"
    _mkdir(directory)
    valid = directory / "valid.conf"
    _write_file(valid, _config_bytes(service_uid, service_gid))
    directory_fd = os.open(directory, DIRECTORY_FLAGS)
    rejected = []
    try:
        os.symlink("valid.conf", "symlink.conf", dir_fd=directory_fd)
        os.mkfifo(directory / "fifo.conf", 0o600)
        os.link(valid, directory / "hardlink.conf", follow_symlinks=False)
        for name, label in (
            ("symlink.conf", "symlink"),
            ("fifo.conf", "fifo"),
            ("hardlink.conf", "hardlink"),
        ):
            try:
                load_probe_config_at(
                    directory_fd,
                    name,
                    expected_service_uid=service_uid,
                    expected_service_gid=service_gid,
                )
            except ProbeConfigRejected:
                rejected.append(label)
            else:
                raise ProbeFailure(f"PR-10 accepted configuration {label}")
    finally:
        os.close(directory_fd)
    return {"rejected": rejected, "rejected_count": len(rejected)}


def _scenario_11_descriptor_anchoring(sandbox: Path) -> dict:
    original = sandbox / "race-parent"
    outside = sandbox / "race-outside"
    _mkdir(original)
    _mkdir(outside)
    _write_file(original / "child", b"anchored-original")
    _write_file(outside / "child", b"outside-sentinel")
    parent_fd, _ = open_directory_path(str(original))
    try:
        held = sandbox / "race-parent-held"
        os.rename(original, held)
        os.symlink(outside, original)
        child_fd = os.open(
            "child", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent_fd
        )
        try:
            data = os.read(child_fd, 128)
        finally:
            os.close(child_fd)
        require(data == b"anchored-original",
                "PR-11 descriptor-relative open escaped to replacement pathname")
        require((outside / "child").read_bytes() == b"outside-sentinel",
                "PR-11 outside sentinel changed")
        return {"descriptor_read": data.decode("ascii"), "replacement_is_symlink": True}
    finally:
        os.close(parent_fd)


def _scenario_12_other_uid_dac(
    sandbox: Path, other_uid: int, other_gid: int
) -> dict:
    source = sandbox / "dac-source"
    destination = sandbox / "dac-destination"
    _mkdir(source)
    command = (
        "import json,os,sys\n"
        "src,dst=sys.argv[1:]\n"
        "def attempt(label, operation):\n"
        " try:\n"
        "  operation()\n"
        "  return [label,0]\n"
        " except OSError as exc:\n"
        "  return [label,exc.errno]\n"
        "print(json.dumps([attempt('rename', lambda: os.rename(src,dst)), "
        "attempt('symlink', lambda: os.symlink('target',dst))]))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command, str(source), str(destination)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=4.0,
        check=False,
        user=other_uid,
        group=other_gid,
        extra_groups=[],
    )
    require(completed.returncode == 0,
            f"PR-12 unprivileged helper failed: {completed.stderr[-500:]}")
    try:
        results = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeFailure("PR-12 helper returned invalid JSON") from exc
    require(len(results) == 2, "PR-12 helper did not attempt both operations")
    for operation, error_number in results:
        require(operation in {"rename", "symlink"}, "PR-12 unknown operation")
        require(error_number in {errno.EACCES, errno.EPERM},
                f"PR-12 {operation} did not fail with DAC denial: {error_number}")
    require(source.is_dir() and not destination.exists(),
            "PR-12 unprivileged helper changed private sandbox")
    return {"other_uid": other_uid, "other_gid": other_gid, "operations_denied": results}


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
    if os.geteuid() != 0:
        print("ERROR: run directly as EUID 0 inside disposable Atlas-VM-test", file=sys.stderr)
        return 2
    if not args.confirm_disposable_vm or not args.confirm_fixture_ids:
        print("ERROR: both disposable-VM and fixture-ID confirmations are required", file=sys.stderr)
        return 2
    ids = (args.service_uid, args.service_gid, args.other_uid, args.other_gid)
    if any(value <= 0 or value > 0xFFFFFFFF for value in ids):
        print("ERROR: fixture IDs must be positive numeric IDs in range", file=sys.stderr)
        return 2
    if args.service_uid == args.other_uid or args.service_gid == args.other_gid:
        print("ERROR: SERVICE and OTHER fixture IDs must differ", file=sys.stderr)
        return 2

    run_info = os.stat("/run", follow_symlinks=False)
    if not stat.S_ISDIR(run_info.st_mode) or run_info.st_uid != 0 or run_info.st_gid != 0:
        print("ERROR: /run is not a root:root directory", file=sys.stderr)
        return 2
    if stat.S_IMODE(run_info.st_mode) & 0o022:
        print("ERROR: /run is writable by group/other; refusing fixture creation", file=sys.stderr)
        return 2

    sandbox_name = None
    sandbox_path: Path | None = None
    sandbox_identity: tuple[int, int] | None = None
    results: list[dict] = []
    started = time.monotonic()
    cleanup = "not-created"

    try:
        sandbox_name = tempfile.mkdtemp(prefix="atlas-path-resolution-", dir="/run")
        sandbox_path = Path(sandbox_name)
        os.chown(sandbox_path, 0, 0, follow_symlinks=False)
        os.chmod(sandbox_path, 0o700)
        sandbox_info = os.stat(sandbox_path, follow_symlinks=False)
        sandbox_identity = (sandbox_info.st_dev, sandbox_info.st_ino)

        fixture_root = sandbox_path / "fixture-root"
        _mkdir(fixture_root)

        scenarios = [
            ("PR-01", _scenario_01_lexical_rejection),
            ("PR-02", lambda: _scenario_02_valid_walk(fixture_root)),
            ("PR-03", lambda: _scenario_03_symlink_ancestors(sandbox_path)),
            ("PR-04", lambda: _scenario_04_non_directory(sandbox_path)),
            ("PR-05", lambda: _scenario_05_writable_ancestors(sandbox_path)),
            ("PR-06", lambda: _scenario_06_wrong_owner(sandbox_path, args.other_uid, args.other_gid)),
            ("PR-07", lambda: _scenario_07_endpoint_owner(sandbox_path, args.service_uid, args.service_gid)),
            ("PR-08", lambda: _scenario_08_endpoint_rejection(
                sandbox_path, args.service_uid, args.service_gid, args.other_uid, args.other_gid
            )),
            ("PR-09", lambda: _scenario_09_config_via_parent_fd(
                sandbox_path, args.service_uid, args.service_gid
            )),
            ("PR-10", lambda: _scenario_10_config_final_objects(
                sandbox_path, args.service_uid, args.service_gid
            )),
            ("PR-11", lambda: _scenario_11_descriptor_anchoring(sandbox_path)),
            ("PR-12", lambda: _scenario_12_other_uid_dac(
                sandbox_path, args.other_uid, args.other_gid
            )),
        ]
        for scenario_id, operation in scenarios:
            try:
                observations = operation()
                results.append({"id": scenario_id, "status": "PASS", "observations": observations})
            except Exception as exc:
                results.append({
                    "id": scenario_id,
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                })
    except Exception as exc:
        results.append({
            "id": "HARNESS",
            "status": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
        })
    finally:
        if sandbox_path is not None and sandbox_identity is not None:
            try:
                current = os.stat(sandbox_path, follow_symlinks=False)
                require(
                    stat.S_ISDIR(current.st_mode)
                    and (current.st_dev, current.st_ino) == sandbox_identity
                    and current.st_uid == 0
                    and stat.S_IMODE(current.st_mode) == 0o700,
                    "sandbox identity changed; refusing cleanup",
                )
                shutil.rmtree(sandbox_path)
                cleanup = "private /run sandbox removed after all child processes exited"
            except Exception as exc:
                cleanup = f"FAILED: {type(exc).__name__}: {exc}"
                results.append({
                    "id": "CLEANUP",
                    "status": "FAIL",
                    "error": cleanup,
                })

    passed = sum(item["status"] == "PASS" for item in results)
    failed = sum(item["status"] == "FAIL" for item in results)
    overall = "PASS" if passed == len(EXPECTED_SCENARIOS) and failed == 0 else "FAIL"
    report = {
        "probe": "A-IPC-03-path-resolution",
        "commit": _git_commit(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "effective_uid": os.geteuid(),
        "fixture_service_uid": args.service_uid,
        "fixture_service_gid": args.service_gid,
        "fixture_other_uid": args.other_uid,
        "fixture_other_gid": args.other_gid,
        "duration_seconds": round(time.monotonic() - started, 3),
        "overall": overall,
        "passed_scenarios": passed,
        "failed_scenarios": failed,
        "cleanup": cleanup,
        "scenarios": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
