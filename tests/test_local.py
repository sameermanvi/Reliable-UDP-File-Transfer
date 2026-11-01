#!/usr/bin/env python3
"""Small localhost tests. Linux netem supplies network faults in the demo."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import json
import select
import socket
import struct
import subprocess
import tempfile
import time
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
CLIENT, SERVER = ROOT / 'src/client', ROOT / 'src/server'
START, START_ACK, DATA, ACK, FIN, FIN_ACK, ERROR = range(1, 8)
HEADER = struct.Struct('!IBBHQII')
TRANSFER_ID = 42


def packet(kind, seq=0, data=b''):
    wire = HEADER.pack(0x52554450, 1, kind, len(data), TRANSFER_ID, seq, 0) + data
    return wire[:20] + struct.pack('!I', zlib.crc32(wire)) + data


def receive(sock):
    global TRANSFER_ID
    wire, peer = sock.recvfrom(2048)
    magic, version, kind, length, TRANSFER_ID, seq, checksum = HEADER.unpack(wire[:24])
    assert magic == 0x52554450 and version == 1 and len(wire) == 24 + length
    assert zlib.crc32(wire[:20] + b'\0' * 4 + wire[24:]) == checksum
    return kind, seq, wire[24:], peer


def udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', 0))
    sock.settimeout(2)
    return sock


def server(output):
    with udp() as reserve:
        port = reserve.getsockname()[1]
    process = subprocess.Popen([str(SERVER), str(port), str(output)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ready, _, _ = select.select([process.stdout], [], [], 3)
    if not ready or not process.stdout.readline().startswith('Listening'):
        process.kill()
        raise AssertionError(process.communicate())
    return process, ('127.0.0.1', port)


def stop(process):
    if process.poll() is None:
        process.kill()
    process.communicate()


class LocalTests(unittest.TestCase):
    def test_binary_sizes(self):
        def transfer(size):
            with tempfile.TemporaryDirectory() as folder:
                folder = Path(folder)
                source, output, trace = folder/'input', folder/'output', folder/'progress'
                data = os.urandom(size)
                source.write_bytes(data)
                receiver, address = server(output)
                try:
                    result = subprocess.run([str(CLIENT), address[0], str(address[1]), str(source)],
                        env=dict(os.environ, RUDP_PROGRESS_LOG=str(trace)), capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    stdout, stderr = receiver.communicate(timeout=12)
                    self.assertEqual(receiver.returncode, 0, stderr)
                    self.assertEqual(output.read_bytes(), data)
                    self.assertIn('bytes=%d ' % size, result.stdout)
                    rows = [(e['monotonic_ns'], e['bytes']) for e in map(json.loads, trace.read_text().splitlines()) if e['event'] == 'ack_progress']
                    self.assertEqual(rows[-1][1] if rows else 0, size)
                    self.assertTrue(all(a[0] <= b[0] and a[1] < b[1] for a, b in zip(rows, rows[1:])))
                finally:
                    stop(receiver)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(transfer, [0, 1, 1023, 1024, 1025, 16384, 16385, 2*1024*1024]))

    def test_receiver_reordering_duplicates_and_bad_packets(self):
        with tempfile.TemporaryDirectory() as folder, udp() as sock:
            output = Path(folder)/'output'
            data = os.urandom(2049)
            receiver, address = server(output)
            try:
                sock.sendto(packet(START, data=struct.pack('!QI', len(data), zlib.crc32(data))), address)
                self.assertEqual(receive(sock)[0], START_ACK)
                # Corrupted/truncated packets must not create ACKs or buffer data.
                bad = packet(DATA, 0, data[:1024])
                sock.sendto(bad[:-1], address)
                sock.sendto(bad[:-1] + bytes([bad[-1] ^ 1]), address)
                for sequence in [1, 1, 2, 0, 0]:
                    sock.sendto(packet(DATA, sequence, data[sequence*1024:(sequence+1)*1024]), address)
                    kind, seq, _, _ = receive(sock)
                    self.assertEqual((kind, seq), (ACK, sequence))
                # Repeating FIN models a lost FIN_ACK without a forwarding proxy.
                for _ in range(3):
                    sock.sendto(packet(FIN, 3), address)
                    self.assertEqual(receive(sock)[:2], (FIN_ACK, 3))
                _, stderr = receiver.communicate(timeout=12)
                self.assertEqual(receiver.returncode, 0, stderr)
                self.assertEqual(output.read_bytes(), data)
            finally:
                stop(receiver)

    def test_sender_retries_only_missing_ack(self):
        with tempfile.TemporaryDirectory() as folder, udp() as sock:
            source = Path(folder)/'input'
            source.write_bytes(os.urandom(4096))
            client = subprocess.Popen([str(CLIENT), '127.0.0.1', str(sock.getsockname()[1]), str(source)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                      env={**os.environ, "RUDP_SACK": "0"})
            try:
                kind, seq, metadata, peer = receive(sock)
                self.assertEqual(kind, START)
                sock.sendto(packet(START_ACK), peer)
                counts, fin_count = {}, 0
                while True:
                    kind, seq, payload, peer = receive(sock)
                    if kind == DATA:
                        counts[seq] = counts.get(seq, 0) + 1
                        self.assertEqual(payload, source.read_bytes()[seq*1024:(seq+1)*1024])
                        if seq != 1 or counts[seq] > 1:
                            sock.sendto(packet(ACK, seq), peer)
                    elif kind == FIN:
                        fin_count += 1
                        if fin_count == 2:
                            sock.sendto(packet(FIN_ACK, seq), peer)
                            break
                stdout, stderr = client.communicate(timeout=3)
                self.assertEqual(client.returncode, 0, stderr)
                self.assertEqual(counts, {0: 1, 1: 2, 2: 1, 3: 1})
                self.assertIn('retransmits=1 ', stdout)
                self.assertIn('control_retransmits=1 ', stdout)
            finally:
                stop(client)

    def test_whole_file_crc_rejection(self):
        with tempfile.TemporaryDirectory() as folder, udp() as sock:
            output = Path(folder)/'output'
            receiver, address = server(output)
            try:
                sock.sendto(packet(START, data=struct.pack('!QI', 1, zlib.crc32(b'x'))), address)
                self.assertEqual(receive(sock)[0], START_ACK)
                sock.sendto(packet(DATA, 0, b'y'), address)
                self.assertEqual(receive(sock)[0], ACK)
                sock.sendto(packet(FIN, 1), address)
                self.assertEqual(receive(sock)[0], ERROR)
                receiver.communicate(timeout=3)
                self.assertNotEqual(receiver.returncode, 0)
                self.assertFalse(output.exists())
            finally:
                stop(receiver)

    def test_existing_output_replaced_only_after_verification(self):
        with tempfile.TemporaryDirectory() as folder, udp() as sock:
            output = Path(folder)/'output'
            output.write_bytes(b'keep me')
            receiver, address = server(output)
            try:
                sock.sendto(packet(START, data=struct.pack('!QI', 0, 0)), address)
                self.assertEqual(receive(sock)[0], START_ACK)
                self.assertEqual(output.read_bytes(), b'keep me')
                sock.sendto(packet(FIN, 0), address)
                self.assertEqual(receive(sock)[0], FIN_ACK)
                receiver.communicate(timeout=12)
                self.assertEqual(receiver.returncode, 0)
                self.assertEqual(output.read_bytes(), b'')
            finally:
                stop(receiver)

    def test_transfer_with_spaces_in_filenames(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / 'input file with spaces.bin'
            output = folder / 'received file with spaces.bin'
            trace = folder / 'progress log.jsonl'
            data = os.urandom(4097)
            source.write_bytes(data)

            receiver, address = server(output)
            try:
                result = subprocess.run(
                    [str(CLIENT), address[0], str(address[1]), str(source)],
                    env=dict(os.environ, RUDP_PROGRESS_LOG=str(trace)),
                    capture_output=True, text=True, timeout=15
                )
                self.assertEqual(result.returncode, 0, result.stderr)

                _, stderr = receiver.communicate(timeout=12)
                self.assertEqual(receiver.returncode, 0, stderr)
                self.assertTrue(output.exists())
                self.assertEqual(output.read_bytes(), data)
            finally:
                stop(receiver)
if __name__ == '__main__':
    unittest.main(verbosity=2)
