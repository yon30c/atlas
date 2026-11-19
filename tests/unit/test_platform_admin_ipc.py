"""Tests for the isolated authority admin Unix IPC prototype."""

import array
import json
import os
import socket
import unittest
import uuid
from unittest.mock import Mock

from atlas.platform_admin_ipc import (
    MAX_JSON_DEPTH,
    MAX_REQUEST_BYTES,
    PROTOCOL_ID,
    AdminIPCError,
    AdminPeerDisconnected,
    AdminPeerRejected,
    AdminProtocolRejected,
    decode_admin_request,
    handle_admin_connection,
    read_peer_credentials,
)


def _request_packet(**overrides):
    value = {
        "protocol": PROTOCOL_ID,
        "request_id": str(uuid.uuid4()),
        "operation": "authority.ping",
        "payload": {},
    }
    value.update(overrides)
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


class AuthorityAdminIPCProtocolTests(unittest.TestCase):
    def test_accepts_only_the_non_mutating_ping_operation(self):
        request = decode_admin_request(_request_packet())
        self.assertEqual(request.protocol, PROTOCOL_ID)
        self.assertEqual(request.operation, "authority.ping")
        self.assertEqual(request.payload, {})

    def test_rejects_unknown_operation_with_stable_code(self):
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(_request_packet(operation="authority.migrate"))
        self.assertEqual(raised.exception.code, "UNKNOWN_OPERATION")

    def test_rejects_extra_request_fields(self):
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(_request_packet(executor_uid=0))
        self.assertEqual(raised.exception.code, "INVALID_REQUEST")

    def test_rejects_non_empty_payload_with_stable_code(self):
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(_request_packet(payload={"path": "/tmp/other.db"}))
        self.assertEqual(raised.exception.code, "INVALID_ARGUMENTS")

    def test_rejects_duplicate_json_keys_as_invalid_json(self):
        request_id = str(uuid.uuid4())
        packet = (
            '{"protocol":"' + PROTOCOL_ID + '","request_id":"' + request_id
            + '","operation":"authority.ping","operation":"authority.migrate","payload":{}}'
        ).encode("utf-8")
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(packet)
        self.assertEqual(raised.exception.code, "INVALID_JSON")

    def test_rejects_numeric_protocol_version(self):
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(_request_packet(protocol=1))
        self.assertEqual(raised.exception.code, "UNSUPPORTED_PROTOCOL_VERSION")

    def test_rejects_unknown_protocol_identifier(self):
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(_request_packet(protocol="atlas-admin/2"))
        self.assertEqual(raised.exception.code, "UNSUPPORTED_PROTOCOL_VERSION")

    def test_rejects_non_canonical_or_non_v4_request_id(self):
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(_request_packet(request_id=str(uuid.uuid1())))
        self.assertEqual(raised.exception.code, "INVALID_REQUEST")

    def test_distinguishes_invalid_utf8_and_invalid_json(self):
        cases = ((bytes([0xFF]), "INVALID_UTF8"), (b"{", "INVALID_JSON"))
        for packet, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(AdminProtocolRejected) as raised:
                    decode_admin_request(packet)
                self.assertEqual(raised.exception.code, expected_code)

    def test_rejects_empty_packet_with_empty_request_code(self):
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(b"")
        self.assertEqual(raised.exception.code, "EMPTY_REQUEST")

    def test_rejects_oversized_packet_with_stable_code(self):
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(b"x" * (MAX_REQUEST_BYTES + 1))
        self.assertEqual(raised.exception.code, "REQUEST_TOO_LARGE")

    def test_rejects_non_finite_json_numbers(self):
        for number in ("NaN", "Infinity", "-Infinity", "1e999"):
            packet = (
                '{"protocol":"' + PROTOCOL_ID + '","request_id":"' + str(uuid.uuid4())
                + '","operation":"authority.ping","payload":{},"extra":' + number + '}'
            ).encode("ascii")
            with self.subTest(number=number):
                with self.assertRaises(AdminProtocolRejected) as raised:
                    decode_admin_request(packet)
                self.assertEqual(raised.exception.code, "INVALID_JSON")

    def test_enforces_json_depth_limit(self):
        request_id = str(uuid.uuid4())
        at_limit = (
            '{"protocol":"' + PROTOCOL_ID + '","request_id":"' + request_id
            + '","operation":"authority.ping","payload":{},"extra":'
            + ("[" * (MAX_JSON_DEPTH - 1)) + "0" + ("]" * (MAX_JSON_DEPTH - 1)) + "}"
        ).encode("ascii")
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(at_limit)
        self.assertEqual(raised.exception.code, "INVALID_REQUEST")

        too_deep = (
            '{"protocol":"' + PROTOCOL_ID + '","request_id":"' + request_id
            + '","operation":"authority.ping","payload":{},"extra":'
            + ("[" * MAX_JSON_DEPTH) + "0" + ("]" * MAX_JSON_DEPTH) + "}"
        ).encode("ascii")
        with self.assertRaises(AdminProtocolRejected) as raised:
            decode_admin_request(too_deep)
        self.assertEqual(raised.exception.code, "INVALID_JSON")


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

    def test_accepts_current_uid_and_returns_contract_response(self):
        packet = _request_packet()
        self.client.send(packet)

        peer, request = handle_admin_connection(
            self.server,
            allowed_peer_uids={os.getuid()},
        )

        response = json.loads(self.client.recv(4096).decode("utf-8"))
        self.assertEqual(peer.uid, os.getuid())
        self.assertEqual(response["protocol"], PROTOCOL_ID)
        self.assertEqual(response["request_id"], request.request_id)
        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["code"], "OK")
        self.assertEqual(response["summary"], "Operation completed")
        self.assertEqual(response["result"], {})
        self.assertIsNone(response["audit_ref"])

    def test_rejects_peer_uid_not_in_allowlist_before_reading_request(self):
        with self.assertRaises(AdminPeerRejected) as raised:
            handle_admin_connection(
                self.server,
                allowed_peer_uids={os.getuid() + 1},
            )
        self.assertEqual(raised.exception.code, "UNAUTHORIZED_PEER")

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

    def test_rejects_non_unix_seqpacket_socket_before_peer_lookup(self):
        connection = Mock()
        connection.family = socket.AF_INET
        with self.assertRaises(AdminProtocolRejected):
            handle_admin_connection(
                connection,
                allowed_peer_uids={os.getuid()},
            )
        connection.getsockopt.assert_not_called()

    def test_validates_read_and_write_timeouts_independently(self):
        with self.assertRaises(AdminProtocolRejected) as raised:
            handle_admin_connection(
                self.server,
                allowed_peer_uids={os.getuid()},
                read_timeout_seconds=1,
                write_timeout_seconds=0,
            )
        self.assertEqual(raised.exception.code, "INVALID_ARGUMENTS")

    def test_rejects_peer_that_does_not_send_before_read_timeout(self):
        with self.assertRaises(AdminIPCError) as raised:
            handle_admin_connection(
                self.server,
                allowed_peer_uids={os.getuid()},
                read_timeout_seconds=0.05,
            )
        self.assertEqual(raised.exception.code, "TIMEOUT")

    def test_rejects_oversized_seqpacket(self):
        self.client.send(b"x" * (MAX_REQUEST_BYTES + 128))
        with self.assertRaises(AdminProtocolRejected) as raised:
            handle_admin_connection(
                self.server,
                allowed_peer_uids={os.getuid()},
            )
        self.assertEqual(raised.exception.code, "MESSAGE_TRUNCATED")

    def test_treats_empty_receive_as_peer_close_without_reply(self):
        self.client.shutdown(socket.SHUT_WR)
        with self.assertRaises(AdminPeerDisconnected):
            handle_admin_connection(
                self.server,
                allowed_peer_uids={os.getuid()},
            )

    @unittest.skipUnless(hasattr(socket, "SCM_RIGHTS"), "SCM_RIGHTS is required")
    def test_rejects_ancillary_file_descriptors_with_stable_code(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        self.client.sendmsg(
            [_request_packet()],
            [
                (
                    socket.SOL_SOCKET,
                    socket.SCM_RIGHTS,
                    array.array("i", [read_fd]),
                )
            ],
        )
        with self.assertRaises(AdminProtocolRejected) as raised:
            handle_admin_connection(
                self.server,
                allowed_peer_uids={os.getuid()},
            )
        self.assertEqual(raised.exception.code, "ANCILLARY_DATA_FORBIDDEN")

    def test_rejects_empty_peer_allowlist(self):
        with self.assertRaises(AdminProtocolRejected):
            handle_admin_connection(self.server, allowed_peer_uids=set())


if __name__ == "__main__":
    unittest.main()
