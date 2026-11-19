"""Experimental Unix SOCK_SEQPACKET boundary for authority admin requests.

This module is a transport/protocol prototype only. It does not open SQLite,
perform administrative operations, create a listening socket, or change UID.
Only the non-mutating authority.ping operation is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import math
import socket
import struct
import uuid
from typing import Any, Mapping


PROTOCOL_ID = "atlas-admin/1"
SERVICE_DISTRIBUTION = "atlas-assistant"
SOURCE_TREE_SERVICE_VERSION = "0.1.0"
MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_JSON_DEPTH = 16
CONNECTION_TIMEOUT_SECONDS = 5.0
MAX_CONNECTION_TIMEOUT_SECONDS = 60.0
_OVERSIZED_JSON_INTEGER = object()
_MAX_UID_VALUE = (1 << (struct.calcsize("I") * 8)) - 1

_CATALOG_OPERATIONS = frozenset({
    "authority.ping",
    "authority.diagnose",
    "authority.migrations.plan",
    "authority.operation.status",
    "authority.initialize",
    "authority.migrations.apply",
    "authority.project_environment.provision",
})
_IMPLEMENTED_OPERATIONS = frozenset({"authority.ping"})
_NO_ERROR_RESPONSE_CODES = frozenset({
    "UNAUTHORIZED_PEER",
    "MESSAGE_TRUNCATED",
    "ANCILLARY_DATA_FORBIDDEN",
})


class AdminIPCError(Exception):
    """Base class for administrative IPC transport failures."""

    def __init__(self, message: str, *, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.code = code


class AdminPeerRejected(AdminIPCError):
    """The kernel-reported peer credentials are not authorized."""

    def __init__(self, message: str = "peer UID is not authorized") -> None:
        super().__init__(message, code="UNAUTHORIZED_PEER")


class AdminPeerDisconnected(AdminIPCError):
    """The peer closed or disappeared; no response can safely be delivered."""

    def __init__(self, message: str = "peer disconnected") -> None:
        super().__init__(message, code="PEER_DISCONNECTED")


class AdminProtocolRejected(AdminIPCError):
    """The packet or decoded request violates the protocol."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "INVALID_REQUEST",
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, code=code)
        self.request_id = request_id


@dataclass(frozen=True, slots=True)
class PeerCredentials:
    """Credentials returned by Linux SO_PEERCRED for the connected peer."""

    pid: int
    uid: int
    gid: int


@dataclass(frozen=True, slots=True)
class AdminRequest:
    """Validated, immutable request accepted by the prototype protocol."""

    protocol: str
    request_id: str
    operation: str
    payload: Mapping[str, Any]


def _service_version() -> str:
    """Return installed distribution metadata, with the source version fallback."""
    try:
        return distribution_version(SERVICE_DISTRIBUTION)
    except PackageNotFoundError:
        # Keep this fallback synchronized with [project].version in pyproject.toml.
        return SOURCE_TREE_SERVICE_VERSION


def _canonical_request_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed_id = uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
    if (
        str(parsed_id) != value
        or parsed_id.version != 4
        or parsed_id.variant != uuid.RFC_4122
    ):
        return None
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AdminProtocolRejected(
                "duplicate JSON object key",
                code="INVALID_JSON",
            )
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> None:
    raise AdminProtocolRejected(
        f"non-standard JSON constant: {value}",
        code="INVALID_JSON",
    )


def _parse_json_integer(value: str) -> int | object:
    """Parse an integer, preserving an invalid sentinel if Python rejects its size."""
    try:
        return int(value)
    except ValueError:
        # Keep the JSON structure parseable so a valid request_id elsewhere in
        # the envelope can still be recovered and attached to INVALID_JSON.
        return _OVERSIZED_JSON_INTEGER


def _validate_json_values_and_depth(value: Any) -> None:
    """Reject oversized integers, non-finite floats and excessive nesting."""
    pending: list[tuple[Any, int]] = [(value, 1)]
    while pending:
        current, depth = pending.pop()
        if current is _OVERSIZED_JSON_INTEGER:
            raise AdminProtocolRejected(
                "JSON integer exceeds the interpreter conversion limit",
                code="INVALID_JSON",
            )
        if isinstance(current, float) and not math.isfinite(current):
            raise AdminProtocolRejected(
                "JSON numbers must be finite",
                code="INVALID_JSON",
            )
        if isinstance(current, dict):
            if depth > MAX_JSON_DEPTH:
                raise AdminProtocolRejected(
                    "JSON nesting exceeds the maximum depth",
                    code="INVALID_JSON",
                )
            pending.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            if depth > MAX_JSON_DEPTH:
                raise AdminProtocolRejected(
                    "JSON nesting exceeds the maximum depth",
                    code="INVALID_JSON",
                )
            pending.extend((child, depth + 1) for child in current)


def decode_admin_request(packet: bytes) -> AdminRequest:
    """Decode one bounded JSON packet and enforce the implemented request schema."""
    if not isinstance(packet, bytes):
        raise AdminProtocolRejected("packet must be bytes")
    if not packet:
        raise AdminProtocolRejected("request packet is empty", code="EMPTY_REQUEST")
    if len(packet) > MAX_REQUEST_BYTES:
        raise AdminProtocolRejected(
            "request exceeds the maximum packet size",
            code="REQUEST_TOO_LARGE",
        )

    try:
        text = packet.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AdminProtocolRejected(
            "request is not valid UTF-8",
            code="INVALID_UTF8",
        ) from exc

    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_constant,
            parse_int=_parse_json_integer,
        )
    except AdminProtocolRejected:
        raise
    except (ValueError, RecursionError) as exc:
        # Parser-level failures must become controlled protocol rejections.
        raise AdminProtocolRejected(
            "request is not valid strict JSON",
            code="INVALID_JSON",
        ) from exc

    safe_request_id = (
        _canonical_request_id(decoded.get("request_id"))
        if isinstance(decoded, dict)
        else None
    )
    try:
        _validate_json_values_and_depth(decoded)
    except AdminProtocolRejected as exc:
        exc.request_id = safe_request_id
        raise

    if not isinstance(decoded, dict):
        raise AdminProtocolRejected("request must be a JSON object")
    if set(decoded) != {"protocol", "request_id", "operation", "payload"}:
        raise AdminProtocolRejected(
            "request contains missing or unknown fields",
            code="INVALID_REQUEST",
            request_id=safe_request_id,
        )

    protocol = decoded["protocol"]
    if not isinstance(protocol, str) or protocol != PROTOCOL_ID:
        raise AdminProtocolRejected(
            "unsupported protocol identifier",
            code="UNSUPPORTED_PROTOCOL_VERSION",
            request_id=safe_request_id,
        )

    request_id = _canonical_request_id(decoded["request_id"])
    if request_id is None:
        raise AdminProtocolRejected(
            "request_id must be a canonical UUIDv4",
            code="INVALID_REQUEST",
        )

    operation = decoded["operation"]
    if not isinstance(operation, str):
        raise AdminProtocolRejected(
            "operation must be a string",
            code="INVALID_REQUEST",
            request_id=request_id,
        )
    if operation not in _CATALOG_OPERATIONS:
        raise AdminProtocolRejected(
            "operation is not in the closed atlas-admin/1 catalog",
            code="UNKNOWN_OPERATION",
            request_id=request_id,
        )
    if operation not in _IMPLEMENTED_OPERATIONS:
        raise AdminProtocolRejected(
            "operation is catalogued but not enabled in this prototype",
            code="OPERATION_DENIED",
            request_id=request_id,
        )

    payload = decoded["payload"]
    if not isinstance(payload, dict) or payload:
        raise AdminProtocolRejected(
            "authority.ping payload must be an empty object",
            code="INVALID_ARGUMENTS",
            request_id=request_id,
        )

    return AdminRequest(
        protocol=PROTOCOL_ID,
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
        struct.calcsize("iII"),
    )
    if len(raw) != struct.calcsize("iII"):
        raise AdminIPCError("kernel returned malformed peer credentials")
    pid, uid, gid = struct.unpack("iII", raw)
    if pid <= 0 or uid < 0 or gid < 0:
        raise AdminIPCError("kernel returned invalid peer credentials")
    return PeerCredentials(pid=pid, uid=uid, gid=gid)


def _validated_timeout(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdminProtocolRejected(
            f"{name} must be a finite positive number",
            code="INVALID_ARGUMENTS",
        )
    try:
        timeout_value = float(value)
    except (OverflowError, ValueError) as exc:
        raise AdminProtocolRejected(
            f"{name} must be a finite positive number",
            code="INVALID_ARGUMENTS",
        ) from exc
    if (
        not math.isfinite(timeout_value)
        or timeout_value <= 0
        or timeout_value > MAX_CONNECTION_TIMEOUT_SECONDS
    ):
        raise AdminProtocolRejected(
            f"{name} must be greater than zero and at most "
            f"{MAX_CONNECTION_TIMEOUT_SECONDS:g}",
            code="INVALID_ARGUMENTS",
        )
    return timeout_value


def _encode_response(response: Mapping[str, Any]) -> bytes:
    try:
        packet = json.dumps(
            dict(response),
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise AdminIPCError(
            "response cannot be encoded",
            code="INTERNAL_ERROR",
        ) from exc
    if len(packet) > MAX_RESPONSE_BYTES:
        raise AdminIPCError(
            "response exceeds the maximum size",
            code="INTERNAL_ERROR",
        )
    return packet


def _send_response(
    connection: socket.socket,
    response: Mapping[str, Any],
    *,
    timeout_seconds: float,
) -> None:
    encoded = _encode_response(response)
    connection.settimeout(timeout_seconds)
    try:
        sent = connection.send(encoded)
    except TimeoutError as exc:
        raise AdminIPCError(
            "response send timed out",
            code="TIMEOUT",
        ) from exc
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as exc:
        raise AdminPeerDisconnected("peer disconnected before response delivery") from exc
    except OSError as exc:
        raise AdminIPCError("response send failed", code="INTERNAL_ERROR") from exc
    if sent != len(encoded):
        raise AdminIPCError(
            "response packet was not sent atomically",
            code="INTERNAL_ERROR",
        )


def handle_admin_connection(
    connection: socket.socket,
    *,
    allowed_peer_uids: frozenset[int] | set[int],
    read_timeout_seconds: float = CONNECTION_TIMEOUT_SECONDS,
    write_timeout_seconds: float = CONNECTION_TIMEOUT_SECONDS,
) -> tuple[PeerCredentials, AdminRequest]:
    """Authenticate one SOCK_SEQPACKET peer and accept one ping request.

    The caller owns the listening socket and connection lifecycle. This
    function never creates files, changes process credentials, or touches DB.
    """
    if connection.family != socket.AF_UNIX:
        raise AdminProtocolRejected(
            "only AF_UNIX connections are supported",
            code="INVALID_REQUEST",
        )
    if connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET:
        raise AdminProtocolRejected(
            "only SOCK_SEQPACKET connections are supported",
            code="INVALID_REQUEST",
        )

    read_timeout = _validated_timeout(
        read_timeout_seconds,
        name="read_timeout_seconds",
    )
    write_timeout = _validated_timeout(
        write_timeout_seconds,
        name="write_timeout_seconds",
    )

    allowed = frozenset(allowed_peer_uids)
    if not allowed or any(
        isinstance(uid, bool) or not isinstance(uid, int) or uid < 0 or uid > _MAX_UID_VALUE
        for uid in allowed
    ):
        raise AdminProtocolRejected(
            "allowed_peer_uids must contain valid UIDs",
            code="INVALID_ARGUMENTS",
        )

    peer = read_peer_credentials(connection)
    if peer.uid not in allowed:
        raise AdminPeerRejected()

    connection.settimeout(read_timeout)
    try:
        packet, ancillary, flags, _address = connection.recvmsg(MAX_REQUEST_BYTES + 1)
    except TimeoutError as exc:
        raise AdminIPCError(
            "request receive timed out",
            code="TIMEOUT",
        ) from exc
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as exc:
        raise AdminPeerDisconnected("peer disconnected while sending request") from exc
    except OSError as exc:
        raise AdminIPCError("request receive failed", code="INTERNAL_ERROR") from exc

    if not packet:
        # SOCK_SEQPACKET may expose both a zero-length packet and orderly EOF
        # as an empty receive. Treat both as transport closure: no operation
        # is executed and no response is sent.
        raise AdminPeerDisconnected("empty receive treated as peer closure")

    if flags & getattr(socket, "MSG_TRUNC", 0):
        raise AdminProtocolRejected(
            "request packet was truncated",
            code="MESSAGE_TRUNCATED",
        )
    if flags & getattr(socket, "MSG_CTRUNC", 0) or ancillary:
        raise AdminProtocolRejected(
            "ancillary data is forbidden",
            code="ANCILLARY_DATA_FORBIDDEN",
        )

    try:
        request = decode_admin_request(packet)
    except AdminProtocolRejected as exc:
        if exc.code not in _NO_ERROR_RESPONSE_CODES:
            _send_response(
                connection,
                {
                    "protocol": PROTOCOL_ID,
                    "request_id": exc.request_id,
                    "status": "rejected",
                    "code": exc.code,
                    "summary": "Request rejected",
                    "result": {},
                    "audit_ref": None,
                },
                timeout_seconds=write_timeout,
            )
        raise

    _send_response(
        connection,
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
        },
        timeout_seconds=write_timeout,
    )
    return peer, request
