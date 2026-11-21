"""Strict temporary configuration fixture for A-IPC-02 MA-07/MA-08.

This is probe-only code. It is not a production Atlas configuration API.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import stat


MAX_CONFIG_BYTES = 4096
MAX_UID_GID = (1 << 32) - 1
_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "service_uid",
        "service_gid",
        "client_uids",
        "socket_path",
        "socket_type",
        "socket_mode",
        "socket_dir_mode",
    }
)
_DECIMAL = re.compile(r"[1-9][0-9]{0,9}\Z")
_MODE = re.compile(r"0[0-7]{3}\Z")


class ProbeConfigRejected(ValueError):
    """A temporary probe configuration failed its closed validation contract."""


@dataclass(frozen=True, slots=True)
class ProbeConfigSnapshot:
    """Immutable values captured from one validated configuration descriptor."""

    schema_version: int
    service_uid: int
    service_gid: int
    client_uids: tuple[int, ...]
    socket_path: str
    socket_type: str
    socket_mode: int
    socket_dir_mode: int


def _positive_id(value: str, name: str) -> int:
    if not _DECIMAL.fullmatch(value):
        raise ProbeConfigRejected(f"{name} must be canonical positive decimal")
    parsed = int(value, 10)
    if parsed > MAX_UID_GID:
        raise ProbeConfigRejected(f"{name} is outside the supported numeric range")
    return parsed


def _socket_path(value: str) -> str:
    if not value.startswith("/") or value.startswith("//") or value.endswith("/"):
        raise ProbeConfigRejected("socket_path must be an absolute canonical path")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ProbeConfigRejected("socket_path must contain ASCII only") from exc
    if len(encoded) > 107:
        raise ProbeConfigRejected("socket_path exceeds the Linux sun_path limit")
    components = value[1:].split("/")
    if any(
        component in {"", ".", ".."}
        or "\\" in component
        or "\x00" in component
        for component in components
    ):
        raise ProbeConfigRejected("socket_path contains an ambiguous component")
    return value


def parse_probe_config(data: bytes) -> ProbeConfigSnapshot:
    """Parse the probe-only key=value grammar; no defaults or extensions."""
    if not isinstance(data, bytes):
        raise ProbeConfigRejected("configuration input must be bytes")
    if not data or len(data) > MAX_CONFIG_BYTES:
        raise ProbeConfigRejected("configuration size is outside the allowed range")
    if not data.endswith(b"\n") or b"\r" in data or b"\x00" in data:
        raise ProbeConfigRejected("configuration requires LF lines and a final newline")
    try:
        text = data.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise ProbeConfigRejected("configuration must be ASCII") from exc

    values: dict[str, str] = {}
    for line in text[:-1].split("\n"):
        if not line or line != line.strip() or line.count("=") != 1:
            raise ProbeConfigRejected("configuration contains a malformed line")
        key, value = line.split("=", 1)
        if not key or not value or any(char.isspace() for char in value):
            raise ProbeConfigRejected("configuration contains an empty or ambiguous value")
        if key not in _REQUIRED_KEYS:
            raise ProbeConfigRejected(f"unknown configuration key: {key}")
        if key in values:
            raise ProbeConfigRejected(f"duplicate configuration key: {key}")
        values[key] = value

    if set(values) != _REQUIRED_KEYS:
        missing = sorted(_REQUIRED_KEYS - set(values))
        raise ProbeConfigRejected(f"configuration is missing required keys: {','.join(missing)}")
    if values["schema_version"] != "1":
        raise ProbeConfigRejected("unsupported configuration schema_version")

    service_uid = _positive_id(values["service_uid"], "service_uid")
    service_gid = _positive_id(values["service_gid"], "service_gid")
    if values["client_uids"] != "0":
        raise ProbeConfigRejected("client_uids must be exactly 0")
    socket_path = _socket_path(values["socket_path"])
    if values["socket_type"] != "SOCK_SEQPACKET":
        raise ProbeConfigRejected("socket_type must be SOCK_SEQPACKET")
    if values["socket_mode"] != "0600":
        raise ProbeConfigRejected("socket_mode must be the probe value 0600")
    if values["socket_dir_mode"] != "0700":
        raise ProbeConfigRejected("socket_dir_mode must be the probe value 0700")
    if not _MODE.fullmatch(values["socket_mode"]) or not _MODE.fullmatch(
        values["socket_dir_mode"]
    ):
        raise ProbeConfigRejected("socket modes must use canonical four-digit octal")

    return ProbeConfigSnapshot(
        schema_version=1,
        service_uid=service_uid,
        service_gid=service_gid,
        client_uids=(0,),
        socket_path=socket_path,
        socket_type="SOCK_SEQPACKET",
        socket_mode=0o600,
        socket_dir_mode=0o700,
    )


def _metadata(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def load_probe_config_at(
    directory_fd: int,
    name: str,
    *,
    expected_service_uid: int,
    expected_service_gid: int,
) -> ProbeConfigSnapshot:
    """Load one root-owned file relative to an already trusted directory fd."""
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ProbeConfigRejected("configuration filename must be one safe path component")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ProbeConfigRejected("O_NOFOLLOW is unavailable")

    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise ProbeConfigRejected(f"configuration open rejected: {exc.errno}") from exc

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ProbeConfigRejected("configuration descriptor is not a regular file")
        if before.st_uid != 0 or before.st_gid != 0:
            raise ProbeConfigRejected("configuration owner must be root:root")
        if stat.S_IMODE(before.st_mode) != 0o644:
            raise ProbeConfigRejected("configuration mode must be exactly 0644 in this probe")
        if before.st_nlink != 1:
            raise ProbeConfigRejected("configuration must have exactly one hard link")
        if before.st_size <= 0 or before.st_size > MAX_CONFIG_BYTES:
            raise ProbeConfigRejected("configuration file size is outside the allowed range")

        chunks: list[bytes] = []
        total = 0
        while total <= MAX_CONFIG_BYTES:
            chunk = os.read(descriptor, min(1024, MAX_CONFIG_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > MAX_CONFIG_BYTES:
            raise ProbeConfigRejected("configuration exceeds the read limit")

        after = os.fstat(descriptor)
        if _metadata(before) != _metadata(after):
            raise ProbeConfigRejected("configuration metadata changed during read")
        snapshot = parse_probe_config(b"".join(chunks))
        if snapshot.service_uid != expected_service_uid:
            raise ProbeConfigRejected("service_uid differs from the expected fixture identity")
        if snapshot.service_gid != expected_service_gid:
            raise ProbeConfigRejected("service_gid differs from the expected fixture identity")
        return snapshot
    finally:
        os.close(descriptor)
