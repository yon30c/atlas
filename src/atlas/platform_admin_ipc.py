"""Experimental Unix SOCK_SEQPACKET boundary for authority admin requests.

This module is a transport/protocol prototype only. It does not open SQLite,
perform administrative operations, create a listening socket, or change UID.
Only the non-mutating authority.ping operation is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
import struct
import uuid
from typing import Any, Mapping


PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 4 * 1024
_ALLOWED_OPERATIONS = frozenset({"authority.ping"})


class AdminIPCError(Exception):
    """Base class for rejected administrative IPC requests."""


class AdminPeerRejected(AdminIPCError):
    """The kernel-reported peer credentials are not authorized."""


class AdminProtocolRejected(AdminIPCError):
    """The packet or decoded request violates the prototype protocol."""


@dataclass(frozen=True, slots=True)
class PeerCredentials:
    """Credentials returned by Linux SO_PEERCRED for the connected peer."""

    pid: int
    uid: int
    gid: int


@dataclass(frozen=True, slots=True)
class AdminRequest:
    """Validated, immutable request accepted by the prototype protocol."""

    version: int
    request_id: str
    operation: str
    payload: Mapping[str, Any]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AdminProtocolRejected("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> None:
    raise AdminProtocolRejected(f"non-standard JSON constant: {value}")


def decode_admin_request(packet: bytes) -> AdminRequest:
    """Decode one bounded JSON packet and enforce the exact prototype schema."""
    if not isinstance(packet, bytes):
        raise AdminProtocolRejected("packet must be bytes")
    if not packet or len(packet) > MAX_REQUEST_BYTES:
        raise AdminProtocolRejected("packet size is outside the allowed range")

    try:
        decoded = json.loads(
            packet.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_constant,
        )
    except AdminProtocolRejected:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AdminProtocolRejected("packet is not valid UTF-8 JSON") from exc

    if not isinstance(decoded, dict):
        raise AdminProtocolRejected("request must be a JSON object")
    if set(decoded) != {"version", "request_id", "operation", "payload"}:
        raise AdminProtocolRejected("request contains missing or unknown fields")

    version = decoded["version"]
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != PROTOCOL_VERSION
    ):
        raise AdminProtocolRejected("unsupported protocol version")

    request_id = decoded["request_id"]
    if not isinstance(request_id, str):
        raise AdminProtocolRejected("request_id must be a string")
    try:
        parsed_id = uuid.UUID(request_id)
    except (ValueError, AttributeError) as exc:
        raise AdminProtocolRejected("request_id must be a canonical UUIDv4") from exc
    if (
        str(parsed_id) != request_id
        or parsed_id.version != 4
        or parsed_id.variant != uuid.RFC_4122
    ):
        raise AdminProtocolRejected("request_id must be a canonical UUIDv4")

    operation = decoded["operation"]
    if not isinstance(operation, str) or operation not in _ALLOWED_OPERATIONS:
        raise AdminProtocolRejected("operation is not available in this prototype")

    payload = decoded["payload"]
    if not isinstance(payload, dict) or payload:
        raise AdminProtocolRejected("authority.ping payload must be an empty object")

    return AdminRequest(
        version=PROTOCOL_VERSION,
        request_id=request_id,
        operation=operation,
        payload={},
    )


def read_peer_credentials(connection: socket.socket) -> PeerCredentials:
    """Read peer PID/UID/GID from the kernel, never from request JSON."""
    if not hasattr(socket, "SO_PEERCRED"):
        raise AdminIPCError("SO_PEERCRED is unavailable on this platform")
    raw = connection.getsockopt(
        socket.SOL_SOCKET,
        socket.SO_PEERCRED,
        struct.calcsize("3i"),
    )
    if len(raw) != struct.calcsize("3i"):
        raise AdminIPCError("kernel returned malformed peer credentials")
    pid, uid, gid = struct.unpack("3i", raw)
    if pid <= 0 or uid < 0 or gid < 0:
        raise AdminIPCError("kernel returned invalid peer credentials")
    return PeerCredentials(pid=pid, uid=uid, gid=gid)


def _encode_response(response: Mapping[str, Any]) -> bytes:
    try:
        packet = json.dumps(
            dict(response),
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise AdminProtocolRejected("response cannot be encoded") from exc
    if len(packet) > MAX_RESPONSE_BYTES:
        raise AdminProtocolRejected("response exceeds the maximum size")
    return packet


def handle_admin_connection(
    connection: socket.socket,
    *,
    allowed_peer_uids: frozenset[int] | set[int],
) -> tuple[PeerCredentials, AdminRequest]:
    """Authenticate one SOCK_SEQPACKET peer and accept one ping request.

    The caller owns the listening socket and connection lifecycle. This
    function never creates files, changes process credentials, or touches DB.
    """
    if connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET:
        raise AdminProtocolRejected("only SOCK_SEQPACKET connections are supported")

    allowed = frozenset(allowed_peer_uids)
    if not allowed or any(
        isinstance(uid, bool) or not isinstance(uid, int) or uid < 0
        for uid in allowed
    ):
        raise AdminProtocolRejected("allowed_peer_uids must contain valid UIDs")

    peer = read_peer_credentials(connection)
    if peer.uid not in allowed:
        raise AdminPeerRejected("peer UID is not authorized")

    packet, _ancillary, flags, _address = connection.recvmsg(MAX_REQUEST_BYTES + 1)
    truncated_flags = getattr(socket, "MSG_TRUNC", 0) | getattr(socket, "MSG_CTRUNC", 0)
    if flags & truncated_flags:
        raise AdminProtocolRejected("request packet or ancillary data was truncated")
    request = decode_admin_request(packet)

    response = {
        "version": PROTOCOL_VERSION,
        "request_id": request.request_id,
        "status": "ok",
        "operation": request.operation,
    }
    encoded = _encode_response(response)
    sent = connection.send(encoded)
    if sent != len(encoded):
        raise AdminIPCError("response packet was not sent atomically")
    return peer, request
