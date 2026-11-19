"""One-shot service used only by the systemd socket-activation integration probe."""

from __future__ import annotations

import os
import socket
import sys

from atlas.platform_admin_ipc import handle_admin_connection


def main() -> int:
    expected_pid = os.getpid()
    if os.environ.get("LISTEN_PID") != str(expected_pid):
        raise RuntimeError("systemd LISTEN_PID does not identify this process")
    if os.environ.get("LISTEN_FDS") != "1":
        raise RuntimeError("expected exactly one activated listener descriptor")

    expected_uid = int(os.environ["ATLAS_EXPECTED_UID"])
    listener = socket.socket(fileno=3)
    if listener.family != socket.AF_UNIX:
        raise RuntimeError("activated descriptor is not AF_UNIX")
    if listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET:
        raise RuntimeError("activated descriptor is not SOCK_SEQPACKET")

    expected_path = os.environ["ATLAS_EXPECTED_SOCKET"]
    if listener.getsockname() != expected_path:
        raise RuntimeError("activated descriptor has an unexpected socket path")

    connection, _ = listener.accept()
    try:
        handle_admin_connection(connection, allowed_peer_uids={expected_uid})
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException as exc:
        print(f"socket activation probe failed: {exc}", file=sys.stderr, flush=True)
        raise
