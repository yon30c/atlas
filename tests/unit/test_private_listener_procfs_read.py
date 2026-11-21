"""Unit tests for bounded procfs reads in the A-IPC-04 probe."""

import importlib.util
from pathlib import Path
import sys
import unittest


_PROBE_PATH = (
    Path(__file__).resolve().parents[1]
    / "integration"
    / "private_unix_listener"
    / "run_stale_recovery_probe.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "atlas_aipc04_stale_recovery_probe", _PROBE_PATH
)
_PROBE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _PROBE
_SPEC.loader.exec_module(_PROBE)


class ChunkedReader:
    """Binary reader that deliberately returns fewer bytes than requested."""

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.read_sizes = []

    def read(self, size):
        self.read_sizes.append(size)
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if len(chunk) > size:
            self.chunks.insert(0, chunk[size:])
            chunk = chunk[:size]
        return chunk


class PrivateListenerProcfsReadTests(unittest.TestCase):
    def test_bounded_reader_accumulates_short_reads_until_eof(self):
        reader = ChunkedReader([b"header", b"row-one", b"row-two"])

        result = _PROBE._read_bounded(reader, 1024)

        self.assertEqual(result, b"headerrow-onerow-two")
        self.assertEqual(len(reader.read_sizes), 4)

    def test_bounded_reader_stops_at_limit_without_reading_more(self):
        reader = ChunkedReader([b"abc", b"def", b"ghi"])

        result = _PROBE._read_bounded(reader, 5)

        self.assertEqual(result, b"abcde")
        self.assertEqual(len(reader.read_sizes), 2)
        self.assertEqual(reader.chunks, [b"f", b"ghi"])

    def test_bounded_reader_accepts_empty_table(self):
        reader = ChunkedReader([])

        self.assertEqual(_PROBE._read_bounded(reader, 32), b"")
        self.assertEqual(len(reader.read_sizes), 1)

    def test_bounded_reader_rejects_negative_limit(self):
        with self.assertRaises(ValueError):
            _PROBE._read_bounded(ChunkedReader([]), -1)


if __name__ == "__main__":
    unittest.main()
