"""Tests for the isolated authority admin Unix IPC prototype."""

import json
import os
import socket
import unittest
import uuid

from atlas.platform_admin_ipc import (
    MAX_REQUEST_BYTES,
    AdminPeerRejected,
    AdminProtocolRejected,
    decode_admin_request,
    handle_admin_connection,
    read_peer_credentials,
)


def _request_packet(**overrides):
    value = {
        "version": 1,
        "request_id": str(uuid.uuid4()),
        "operation": "authority.ping",
        "payload": {},
    }
    value.update(overrides)
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


class AuthorityAdminIPCProtocolTests(unittest.TestCase):
    def test_accepts_only_the_non_mutating_ping_operation(self):
        request = decode_admin_request(_request_packet())
        self.assertEqual(request.operation, "authority.ping")
        self.assertEqual(request.payload, {})

    def test_rejects_unknown_operation(self):
        with self.assertRaises(AdminProtocolRejected):
            decode_admin_request(_request_packet(operation="authority.migrate"))

    def test_rejects_extra_request_fields(self):
        with self.assertRaises(AdminProtocolRejected):
            decode_admin_request(_request_packet(executor_uid=0))

    def test_rejects_non_empty_payload(self):
        with self.assertRaises(AdminProtocolRejected):
            decode_admin_request(_request_packet(payload={"path": "/tmp/other.db"}))

    def test_rejects_duplicate_json_keys(self):
        request_id = str(uuid.uuid4())
        packet = (
            '{"version":1,"request_id":"' + request_id
            + '","operation":"authority.ping","operation":"authority.migrate","payload":{}}'
        ).encode("utf-8")
        with self.assertRaises(AdminProtocolRejected):
            decode_admin_request(packet)

    def test_rejects_boolean_protocol_version(self):
        with self.assertRaises(AdminProtocolRejected):
            decode_admin_request(_request_packet(version=True))

    def test_rejects_float_protocol_version(self):
        with self.assertRaises(AdminProtocolRejected):
            decode_admin_request(_request_packet(version=1.0))

    def test_rejects_non_canonical_or_non_v4_request_id(self):
        with self.assertRaises(AdminProtocolRejected):
            decode_admin_request(_request_packet(request_id=str(uuid.uuid1())))

    def test_rejects_invalid_utf8_and_non_json(self):
        for packet in (bytes([0xFF]), b"{"):
            with self.subTest(packet=packet):
                with self.assertRaises(AdminProtocolRejected):
                    decode_admin_request(packet)

    def test_rejects_empty_and_oversized_packets(self):
        for packet in (bytes([0xFF]), b"{"):
            with self.subTest(size=len(packet)):
                with self.assertRaises(AdminProtocolRejected):
                    decode_admin_request(packet)


@unittest.skipUnless(
    hasattr(socket, "SO_PEERCRED") and hasattr(socket, "SOCK_SEQPACKET"),
    "Linux Unix SOCK_SEQPACKET and SO_PEERCRED are required",
)
class AuthorityAdminIPCPeerTests(unittest.TestCase):
    def setUp(self):
        self.server, self.client = socket.socketpair(
            socket.AF_UNIX,
            socket.SOCK_SEQPACKET,
        )
        self.addCleanup(self.server.close)
        self.addCleanup(self.client.close)

    def test_reads_peer_credentials_from_kernel(self):
        peer = read_peer_credentials(self.server)
        self.assertEqual(peer.uid, os.getuid())
        self.assertEqual(peer.gid, os.getgid())
        self.assertGreater(peer.pid, 0)

    def test_accepts_current_uid_and_returns_one_packet_response(self):
        packet = _request_packet()
        self.client.send(packet)

        peer, request = handle_admin_connection(
            self.server,
            allowed_peer_uids={os.getuid()},
        )

        response = json.loads(self.client.recv(4096).decode("utf-8"))
        self.assertEqual(peer.uid, os.getuid())
        self.assertEqual(response["request_id"], request.request_id)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["operation"], "authority.ping")

    def test_rejects_peer_uid_not_in_allowlist_before_reading_request(self):
        with self.assertRaises(AdminPeerRejected):
            handle_admin_connection(
                self.server,
                allowed_peer_uids={os.getuid() + 1},
            )

    def test_rejects_stream_socket(self):
        stream_server, stream_client = socket.socketpair(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )
        self.addCleanup(stream_server.close)
        self.addCleanup(stream_client.close)
        with self.assertRaises(AdminProtocolRejected):
            handle_admin_connection(
                stream_server,
                allowed_peer_uids={os.getuid()},
            )

    def test_rejects_oversized_seqpacket(self):
        self.client.send(b"x" * (MAX_REQUEST_BYTES + 128))
        with self.assertRaises(AdminProtocolRejected):
            handle_admin_connection(
                self.server,
                allowed_peer_uids={os.getuid()},
            )

    def test_rejects_empty_peer_allowlist(self):
        with self.assertRaises(AdminProtocolRejected):
            handle_admin_connection(self.server, allowed_peer_uids=set())


if __name__ == "__main__":
    unittest.main()
