"""Adversarial sender tests using an independent Python wire peer."""
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest
import zlib
from test_protocol import CLIENT, DATA, ACK, FIN, FIN_ACK, START_ACK, HEADER, frame, stop


class TransportTests(unittest.TestCase):
    def peer_test(self, handler, size=4096, **settings):
        with tempfile.TemporaryDirectory() as directory, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1', 0)); sock.settimeout(10)
            source, trace = Path(directory)/'input', Path(directory)/'trace'
            source.write_bytes(b'x' * size)
            env = {**os.environ, 'RUDP_RTO': 'adaptive', 'RUDP_CC': '0', 'RUDP_SACK': '1',
                   'RUDP_PROGRESS_LOG': str(trace), **settings}
            client = subprocess.Popen([str(CLIENT), '127.0.0.1', str(sock.getsockname()[1]), str(source)],
                                      env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                start, address = sock.recvfrom(4096)
                header = HEADER.unpack(start[:24]); transfer = header[4]
                def send(kind, seq=0, payload=b''):
                    sock.sendto(frame(kind, transfer, seq, payload), address)
                def receive():
                    wire, _ = sock.recvfrom(4096)
                    return HEADER.unpack(wire[:24])[2], HEADER.unpack(wire[:24])[5]
                handler(sock, send, receive, header, client, trace)
                stdout, stderr = client.communicate(timeout=10)
                self.assertEqual(client.returncode, 0, stdout + stderr)
                return [json.loads(line) for line in trace.read_text().splitlines()]
            finally:
                stop(client)

    def test_negotiation_invalid_sack_and_duplicate_ack_evidence(self):
        def handler(sock, send, receive, start, client, trace):
            self.assertEqual(start[2], 8)
            # Legacy START_ACK cannot negotiate bitmap mode.
            send(START_ACK)
            self.assertEqual(receive()[0], 8)
            send(9)
            self.assertEqual({receive() for _ in range(4)}, {(DATA, i) for i in range(4)})
            for payload in (b'bad', struct.pack('!II', 5, 0), struct.pack('!II', 0, 1),
                            struct.pack('!II', 3, 4), struct.pack('!II', 0, 0)):
                send(10, 0, payload)
            # Three copies of the same later ACK must not count as three new gaps.
            for _ in range(3): send(10, 3, struct.pack('!II', 0, 8))
            # ACK only packet 0: if an invalid cumulative report had mutated the
            # window, the sender would incorrectly FIN instead of retrying 1/2.
            send(10, 0, struct.pack('!II', 1, 4))
            missing = set()
            while missing != {1, 2}:
                kind, seq = receive()
                self.assertEqual(kind, DATA)
                missing.add(seq)
                send(10, seq, struct.pack('!II', seq + 1, 0) if seq == 2 else struct.pack('!II', 2, 2))
            self.assertEqual(receive(), (FIN, 4)); send(FIN_ACK, 4)
        events = self.peer_test(handler)
        self.assertTrue(any(e['event'] == 'ack_rejected' for e in events))
        self.assertFalse(any(e['event'] == 'retransmit' and e['reason'] == 'fast_gap' for e in events))

    def test_karn_and_backoff_cap(self):
        def handler(sock, send, receive, start, client, trace):
            send(9)
            self.assertEqual(receive(), (DATA, 0))
            # Hold the ACK until per-packet backoff reaches 2 s. Never let a
            # retransmitted packet supply an apparently unambiguous RTT sample.
            while True:
                self.assertEqual(receive(), (DATA, 0))
                events = [json.loads(line) for line in trace.read_text().splitlines()]
                if any(e['event'] == 'retransmit' and e['value'] == 2000 for e in events):
                    break
            send(10, 0, struct.pack('!II', 1, 0))
            self.assertEqual(receive(), (FIN, 1)); send(FIN_ACK, 1)
        events = self.peer_test(handler, size=1)
        updates = [e for e in events if e['event'] == 'rto_update']
        self.assertTrue(updates)
        self.assertTrue(all(50 <= e['value'] <= 2000 for e in updates))
        self.assertFalse(any(e['reason'] == 'rtt_sample' for e in updates))

    def test_clean_rtt_floor_and_cwnd_cap(self):
        def handler(sock, send, receive, start, client, trace):
            send(9)
            while True:
                kind, seq = receive()
                if kind == FIN:
                    send(FIN_ACK, seq); break
                self.assertEqual(kind, DATA)
                send(ACK, seq)
        events = self.peer_test(handler, size=64*1024, RUDP_CC='1')
        updates = [e for e in events if e['event'] == 'rto_update']
        self.assertTrue(any(e['reason'] == 'rtt_sample' for e in updates))
        self.assertTrue(all(50 <= e['value'] <= 2000 for e in updates))
        self.assertTrue(all(1 <= e['value'] <= 32 for e in events if e['event'] == 'cwnd_change'))

    def test_fixed_mode_and_legacy_wire(self):
        def handler(sock, send, receive, start, client, trace):
            self.assertEqual(start[2], 1); send(START_ACK)
            self.assertEqual(receive(), (DATA, 0))
            # Unnegotiated bitmap cannot ACK anything in plain mode.
            send(10, 0, struct.pack('!II', 1, 0))
            self.assertEqual(receive(), (DATA, 0)); send(ACK, 0)
            self.assertEqual(receive(), (FIN, 1)); send(FIN_ACK, 1)
        events = self.peer_test(handler, size=1, RUDP_RTO='fixed', RUDP_SACK='0')
        self.assertFalse(any(e['event'] == 'rto_update' for e in events))
        self.assertTrue(all(e['value'] == 200 for e in events if e['event'] == 'retransmit'))

    def test_invalid_rto_setting(self):
        result = subprocess.run([str(CLIENT), '127.0.0.1', '9000', '/missing'],
                                env={**os.environ, 'RUDP_RTO': 'typo'}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('RUDP_RTO must be', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
