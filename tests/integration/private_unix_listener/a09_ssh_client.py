#!/usr/bin/python3
"""Fixed, stdlib-only SSH forced-command client for the A-IPC-01 A09 probe.

This helper accepts one bounded JSON instruction on stdin. It never executes
commands, changes credentials, reads the checkout, or mutates socket paths.
"""
from __future__ import annotations

import errno
import json
import os
import socket
import sys
import uuid

MAX_CONTROL_BYTES = 4096
MAX_SOCKET_PATH_BYTES = 100
MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 64 * 1024


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_instruction() -> dict[str, object]:
    raw = sys.stdin.buffer.read(MAX_CONTROL_BYTES + 1)
    if len(raw) > MAX_CONTROL_BYTES:
        raise ValueError("instruction too large")
    value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object)
    if not isinstance(value, dict) or set(value) != {"scenario", "socket_path", "nonce"}:
        raise ValueError("invalid instruction schema")
    scenario = value["scenario"]
    path = value["socket_path"]
    nonce = value["nonce"]
    if scenario not in {"A09a", "A09b"}:
        raise ValueError("unsupported scenario")
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
        raise ValueError("invalid socket path")
    if len(os.fsencode(path)) >= MAX_SOCKET_PATH_BYTES:
        raise ValueError("socket path exceeds AF_UNIX limit")
    if not isinstance(nonce, str) or len(nonce) != 32:
        raise ValueError("invalid nonce")
    try:
        int(nonce, 16)
    except ValueError as exc:
        raise ValueError("invalid nonce") from exc
    if os.environ.get("SSH_ORIGINAL_COMMAND", ""):
        raise ValueError("unexpected original SSH command")
    return value


def _emit(value: dict[str, object]) -> None:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("ascii")
    if len(encoded) > 2048:
        raise ValueError("result too large")
    sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()


def _run(instruction: dict[str, object]) -> dict[str, object]:
    scenario = str(instruction["scenario"])
    path = str(instruction["socket_path"])
    result: dict[str, object] = {
        "scenario": scenario,
        "nonce": instruction["nonce"],
        "pid": os.getpid(),
        "uid": os.getuid(),
        "gid": os.getgid(),
    }
    client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    client.settimeout(2.0)
    try:
        try:
            client.connect(path)
        except OSError as exc:
            result["connect_errno"] = exc.errno
            result["connected"] = False
            if scenario == "A09b":
                raise
            return result

        result["connect_errno"] = None
        result["connected"] = True
        if scenario == "A09a":
            return result

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
        if len(packet) > MAX_REQUEST_BYTES:
            raise ValueError("generated request exceeds protocol limit")
        client.sendall(packet)
        try:
            response = client.recv(1)
        except (ConnectionResetError, ConnectionAbortedError):
            response = b""
            result["closure"] = "reset"
        else:
            result["closure"] = "eof" if not response else "response"
        result["bytes_received"] = len(response)
        result["peer_closed"] = not response
        return result
    finally:
        client.close()


def main() -> int:
    try:
        instruction = _read_instruction()
        result = _run(instruction)
        _emit(result)
        return 0
    except BaseException as exc:
        # A fixed error object keeps stdout machine-readable. Do not echo input,
        # paths, environment values, or key material.
        try:
            _emit({"error": type(exc).__name__, "message": "A09 helper failed"})
        except BaseException:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
