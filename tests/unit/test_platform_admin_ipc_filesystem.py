"""Filesystem-socket boundary tests for the authority admin IPC prototype.

These tests exercise temporary AF_UNIX paths only. They do not create a
persistent Atlas listener or touch host service paths.
"""

import json
import os
import socket
import stat
import tempfile
import unittest
import uuid

from atlas.platform_admin_ipc import (
    PROTOCOL_ID,
    AdminPeerDisconnected,
    AdminPeerRejected,
    handle_admin_connection,
)


def _ping_packet():
    return json.dumps(
        {
            "protocol": PROTOCOL_ID,
            "request_id": str(uuid.uuid4()),
            "operation": "authority.ping",
            "payload": {},
        },
        separators=(",", ":"),
    ).encode("utf-8")


class AuthorityAdminIPCFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="atlas-admin-ipc-")
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self._remove_socket_path)
        self.directory = self.temp_dir.name
        os.chmod(self.directory, 0o700)
        self.socket_path = os.path.join(self.directory, "admin.sock")

    def _remove_socket_path(self):
        if os.path.lexists(self.socket_path):
            os.unlink(self.socket_path)

    def test_temporary_seqpacket_socket_has_explicit_private_mode(self):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(listener.close)

        listener.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)

        directory_mode = stat.S_IMODE(os.stat(self.directory).st_mode)
        socket_mode = stat.S_IMODE(os.stat(self.socket_path).st_mode)
        self.assertEqual(directory_mode, 0o700)
        self.assertEqual(socket_mode, 0o600)
        self.assertEqual(
            listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE),
            socket.SOCK_SEQPACKET,
        )

    def test_bind_does_not_replace_a_preexisting_regular_file(self):
        with open(self.socket_path, "wb") as existing:
            existing.write(b"do-not-replace")

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(listener.close)
        with self.assertRaises(OSError):
            listener.bind(self.socket_path)

        with open(self.socket_path, "rb") as existing:
            self.assertEqual(existing.read(), b"do-not-replace")

    def test_bind_does_not_replace_a_preexisting_symlink(self):
        target = os.path.join(self.directory, "target")
        with open(target, "wb") as existing:
            existing.write(b"symlink-target")
        os.symlink(target, self.socket_path)

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(listener.close)
        with self.assertRaises(OSError):
            listener.bind(self.socket_path)

        self.assertTrue(os.path.islink(self.socket_path))
        with open(target, "rb") as existing:
            self.assertEqual(existing.read(), b"symlink-target")

    def test_filesystem_socket_accepts_one_ping_and_returns_contract_response(self):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(listener.close)
        listener.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        listener.listen(1)
        listener.settimeout(2.0)

        client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(client.close)
        client.settimeout(2.0)
        client.connect(self.socket_path)
        client.sendall(_ping_packet())

        connection, _ = listener.accept()
        self.addCleanup(connection.close)
        peer, request = handle_admin_connection(
            connection,
            allowed_peer_uids={os.getuid()},
        )

        response = json.loads(client.recv(4096).decode("utf-8"))
        self.assertEqual(peer.uid, os.getuid())
        self.assertEqual(response["protocol"], PROTOCOL_ID)
        self.assertEqual(response["request_id"], request.request_id)
        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["code"], "OK")
        self.assertEqual(response["summary"], "Operation completed")
        self.assertIsNone(response["audit_ref"])

        result = response["result"]
        self.assertEqual(result["protocol_version"], PROTOCOL_ID)
        self.assertIsInstance(result["service_version"], str)
        self.assertTrue(result["service_version"])
        self.assertEqual(result["handler_status"], "available")
        self.assertEqual(
            set(result),
            {"protocol_version", "service_version", "handler_status"},
        )

    def test_disconnect_before_request_is_reported_as_peer_disconnect(self):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(listener.close)
        listener.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        listener.listen(1)
        listener.settimeout(2.0)

        client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        client.connect(self.socket_path)
        connection, _ = listener.accept()
        client.close()
        self.addCleanup(connection.close)

        with self.assertRaises(AdminPeerDisconnected):
            handle_admin_connection(
                connection,
                allowed_peer_uids={os.getuid()},
            )

    @unittest.skipUnless(
        hasattr(os, "fork") and os.geteuid() == 0,
        "requires Linux root to create a peer with a different UID",
    )
    def test_rejects_connection_from_a_real_process_with_another_uid(self):
        try:
            import pwd

            unprivileged = pwd.getpwnam("nobody")
        except KeyError:
            self.skipTest("the nobody account is unavailable")

        os.chmod(self.directory, 0o755)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(listener.close)
        listener.bind(self.socket_path)
        os.chmod(self.socket_path, 0o666)
        listener.listen(1)
        listener.settimeout(5.0)

        child_pid = os.fork()
        if child_pid == 0:
            try:
                listener.close()
                os.setgid(unprivileged.pw_gid)
                os.setuid(unprivileged.pw_uid)
                client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                client.connect(self.socket_path)
                client.sendall(_ping_packet())
                client.close()
                os._exit(0)
            except BaseException:
                os._exit(1)

        try:
            connection, _ = listener.accept()
            self.addCleanup(connection.close)
            with self.assertRaises(AdminPeerRejected):
                handle_admin_connection(
                    connection,
                    allowed_peer_uids={os.getuid()},
                )
        finally:
            _pid, status = os.waitpid(child_pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)


if __name__ == "__main__":
    unittest.main()
