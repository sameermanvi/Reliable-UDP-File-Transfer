#!/usr/bin/env python3
"""Local integration tests; no root, external packages, or network emulator needed."""
import concurrent.futures
import hashlib
import heapq
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
CLIENT, SERVER = ROOT / 'src/client', ROOT / 'src/server'
HEADER = struct.Struct('!IBBHQII')
START, START_ACK, DATA, ACK, FIN, FIN_ACK, ERROR = range(1, 8)


def frame(kind, transfer=42, sequence=0, payload=b'', version=1):
    wire = HEADER.pack(0x52554450, version, kind, len(payload), transfer, sequence, 0) + payload
    return wire[:20] + struct.pack('!I', zlib.crc32(wire)) + wire[24:]


def port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def start_server(number, output):
    process = subprocess.Popen([str(SERVER), str(number), str(output)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ready, _, _ = select.select([process.stdout], [], [], 3)
    if not ready or not process.stdout.readline().startswith('Listening'):
        process.kill()
        raise AssertionError('Server failed to listen: ' + str(process.communicate()))
    return process


def stop(process):
    if process.poll() is None:
        process.terminate()
    process.communicate(timeout=3)


class ImpairmentProxy(threading.Thread):
    """Deterministic bidirectional faults, including repeated FIN_ACK loss."""
    def __init__(self, server_port):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        self.server = ('127.0.0.1', server_port)
        self.client = None
        self.done = threading.Event()
        self.counts = {}
        self.actions = set()
        self.failure = None
        self.pending = []
        self.serial = 0

    def run(self):
        try:
            while not self.done.is_set():
                now = time.monotonic()
                while self.pending and self.pending[0][0] <= now:
                    _, _, wire, destination = heapq.heappop(self.pending)
                    self.sock.sendto(wire, destination)
                ready, _, _ = select.select([self.sock], [], [], .01)
                if not ready:
                    continue
                wire, source = self.sock.recvfrom(65535)
                if source == self.server:
                    destination, direction = self.client, 'back'
                else:
                    self.client = source
                    destination, direction = self.server, 'forward'
                _, _, kind, _, _, sequence, _ = HEADER.unpack(wire[:24])
                key = direction, kind, sequence
                count = self.counts[key] = self.counts.get(key, 0) + 1
                if ((kind in (START, START_ACK, FIN) and count == 1) or
                    (kind == FIN_ACK and count <= 4) or
                    (kind == DATA and sequence == 2 and count == 1) or
                    (kind == ACK and sequence == 5 and count == 1)):
                    self.actions.add('loss')
                    if kind == FIN_ACK:
                        self.actions.add('fin_ack_loss')
                    continue
                if kind == DATA and sequence == 3 and count == 1:
                    wire = wire[:-1] + bytes([wire[-1] ^ 1])
                    self.actions.add('corruption')
                if kind == DATA and sequence == 1 and count == 1:
                    self.serial += 1
                    heapq.heappush(self.pending, (now + .08, self.serial, wire, destination))
                    self.actions.add('reordering')
                    continue
                self.sock.sendto(wire, destination)
                if kind in (DATA, ACK) and sequence == 4 and count == 1:
                    self.sock.sendto(wire, destination)
                    self.actions.add('duplication')
        except Exception as error:
            self.failure = error

    def close(self):
        self.done.set()
        self.join(timeout=2)
        self.sock.close()
        if self.failure:
            raise self.failure


class ProtocolTests(unittest.TestCase):
    def transfer(self, size, impaired=False):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'input', Path(directory) / 'output'
            content = bytes(range(256)) * (size // 256) + bytes(range(size % 256))
            source.write_bytes(content)
            number = port()
            server = start_server(number, target)
            proxy = ImpairmentProxy(number) if impaired else None
            try:
                if proxy:
                    proxy.start()
                progress = Path(directory) / 'progress.jsonl'
                before = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
                client = subprocess.run([str(CLIENT), '127.0.0.1', str(proxy.port if proxy else number), str(source)],
                                        capture_output=True, text=True, timeout=20,
                                        env={**os.environ, 'RUDP_PROGRESS_LOG': str(progress)})
                after = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
                self.assertEqual(client.returncode, 0, client.stdout + client.stderr)
                events = [json.loads(line) for line in progress.read_text().splitlines()]
                events = [e for e in events if e['event'] == 'ack_progress']
                self.assertEqual(bool(events), bool(size))
                last_base, last_stamp = 0, before
                for event in events:
                    self.assertEqual(event['event'], 'ack_progress')
                    self.assertGreater(event['base'], last_base)
                    self.assertGreaterEqual(event['monotonic_ns'], last_stamp)
                    self.assertLessEqual(event['monotonic_ns'], after)
                    self.assertEqual(event['bytes'], min(event['base'] * 1024, size))
                    last_base, last_stamp = event['base'], event['monotonic_ns']
                if events:
                    self.assertEqual(events[-1]['bytes'], size)
                stdout, stderr = server.communicate(timeout=9)
                self.assertEqual(server.returncode, 0, stdout + stderr)
                self.assertEqual(target.read_bytes(), content)
                self.assertEqual(hashlib.sha256(target.read_bytes()).digest(), hashlib.sha256(content).digest())
                self.assertIn(f'crc32={zlib.crc32(content):08x}', client.stdout)
                self.assertFalse(list(Path(directory).glob('*.part.*')))
                if proxy:
                    self.assertEqual(proxy.actions, {'loss', 'fin_ack_loss', 'corruption', 'reordering', 'duplication'})
                    self.assertNotIn('retransmits=0 ', client.stdout)
                return size, impaired
            finally:
                stop(server)
                if proxy:
                    proxy.close()

    def test_file_sizes_and_faults(self):
        # Concurrent independent sessions keep the fixed FIN linger from slowing the suite.
        cases = [(size, False) for size in (0, 1, 1023, 1024, 1025, 32768, 32769, 1048576)]
        cases += [(32769, True), (262267, True)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(self.transfer, *case) for case in cases]
            for future in futures:
                size, impaired = future.result()
                print(f'  verified {size} bytes, faults={impaired}', flush=True)

    def test_sack_window_edges_and_cumulative_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'output'
            number = port()
            server = start_server(number, target)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(2)
                    address = ('127.0.0.1', number)
                    sock.sendto(frame(8, payload=struct.pack('!QI', 32768, 0)), address)
                    self.assertEqual(HEADER.unpack(sock.recv(4096)[:24])[2], 9)
                    for seq, expected_base, expected_bitmap in [(31, 0, 1 << 31),
                                                               (1, 0, (1 << 31) | 2),
                                                               (0, 2, 1 << 29),
                                                               (0, 2, 1 << 29)]:
                        sock.sendto(frame(DATA, sequence=seq, payload=b'x' * 1024), address)
                        wire = sock.recv(4096)
                        self.assertEqual(HEADER.unpack(wire[:24])[2], 10)
                        self.assertEqual(HEADER.unpack(wire[:24])[5], seq)
                        self.assertEqual(struct.unpack('!II', wire[24:]), (expected_base, expected_bitmap))
                    self.assertFalse(target.exists())
            finally:
                stop(server)

    def test_argument_validation(self):
        for value in ('0', '-1', '65536', '99999999999999999999', 'abc', '12x', '+80'):
            for binary, args in ((CLIENT, ['127.0.0.1', value, '/missing']), (SERVER, [value, '/missing'])):
                result = subprocess.run([str(binary), *args], capture_output=True, timeout=2)
                self.assertNotEqual(result.returncode, 0)
        result = subprocess.run([str(CLIENT), 'invalid', '9000', '/missing'], capture_output=True, timeout=2)
        self.assertIn(b'Invalid IPv4', result.stderr)

    def test_progress_log_never_overwrites_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input'
            source.write_bytes(b'keep this input')
            result = subprocess.run([str(CLIENT), '127.0.0.1', '9000', str(source)],
                                    capture_output=True, timeout=2,
                                    env={**os.environ, 'RUDP_PROGRESS_LOG': str(source)})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'create progress log', result.stderr)
            self.assertEqual(source.read_bytes(), b'keep this input')

    def test_receiver_validation_and_session_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'output'
            target.write_bytes(b'previous contents')
            number = port()
            server = start_server(number, target)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            stranger = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(.15)
            address = ('127.0.0.1', number)
            try:
                def expect_silence(wire):
                    sock.sendto(wire, address)
                    with self.assertRaises(socket.timeout):
                        sock.recv(4096)

                # Garbage, truncated, oversized and corrupted datagrams must not start a session.
                for wire in (b'garbage', frame(START, payload=struct.pack('!QI', 0, 0), version=2), frame(START)[:20], frame(START, payload=b'x' * 1025),
                             frame(START, payload=struct.pack('!QI', 0, 0))[:-1] + b'\x01'):
                    expect_silence(wire)
                self.assertEqual(target.read_bytes(), b'previous contents')
                content = b'test data'
                sock.sendto(frame(START, payload=struct.pack('!QI', len(content), zlib.crc32(content))), address)
                self.assertEqual(HEADER.unpack(sock.recv(4096)[:24])[2], START_ACK)
                stranger.sendto(frame(DATA, payload=content), address)
                expect_silence(frame(DATA, transfer=99, payload=content))
                expect_silence(frame(DATA, payload=b'bad length'))
                expect_silence(frame(FIN, sequence=1))
                expect_silence(frame(DATA, sequence=100, payload=content))
                sock.sendto(frame(DATA, payload=content), address)
                self.assertEqual(HEADER.unpack(sock.recv(4096)[:24])[2], ACK)
                self.assertEqual(target.read_bytes(), b'previous contents')
                sock.sendto(frame(FIN, sequence=1), address)
                self.assertEqual(HEADER.unpack(sock.recv(4096)[:24])[2], FIN_ACK)
                stdout, stderr = server.communicate(timeout=9)
                self.assertEqual(server.returncode, 0, stdout + stderr)
                self.assertEqual(target.read_bytes(), content)
            finally:
                sock.close()
                stranger.close()
                stop(server)

    def test_whole_file_checksum_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'output'
            target.write_bytes(b'keep me')
            number = port()
            server = start_server(number, target)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(2)
                    address = ('127.0.0.1', number)
                    sock.sendto(frame(START, payload=struct.pack('!QI', 4, 0)), address)
                    sock.recv(4096)
                    sock.sendto(frame(DATA, payload=b'data'), address)
                    sock.recv(4096)
                    sock.sendto(frame(FIN, sequence=1), address)
                    self.assertEqual(HEADER.unpack(sock.recv(4096)[:24])[2], ERROR)
                server.communicate(timeout=2)
                self.assertNotEqual(server.returncode, 0)
                self.assertEqual(target.read_bytes(), b'keep me')
                self.assertFalse(list(Path(directory).glob('*.part.*')))
            finally:
                stop(server)

    def test_missing_fin_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'output'
            target.write_bytes(b'keep me')
            number = port()
            server = start_server(number, target)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(2)
                    address = ('127.0.0.1', number)
                    sock.sendto(frame(START, payload=struct.pack('!QI', 0, 0)), address)
                    sock.recv(4096)
                _, stderr = server.communicate(timeout=12)
                self.assertNotEqual(server.returncode, 0)
                self.assertIn('transfer incomplete', stderr)
                self.assertEqual(target.read_bytes(), b'keep me')
                self.assertFalse(list(Path(directory).glob('*.part.*')))
            finally:
                stop(server)

    def test_unavailable_server_is_bounded_failure(self):
        # Bind but never respond, so the result does not depend on ICMP handling.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as blackhole, tempfile.TemporaryDirectory() as directory:
            blackhole.bind(('127.0.0.1', 0))
            source = Path(directory) / 'input'
            source.write_bytes(b'data')
            result = subprocess.run([str(CLIENT), '127.0.0.1', str(blackhole.getsockname()[1]), str(source)],
                                    capture_output=True, text=True, timeout=9)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('after 30 retries', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
