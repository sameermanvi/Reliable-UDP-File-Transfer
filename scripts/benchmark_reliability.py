#!/usr/bin/env python3
"""Deterministic localhost ablations. No SDN claims; each output is SHA-256 checked."""
import argparse
import csv
import hashlib
import heapq
import importlib.util
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('experiments', ROOT / 'scripts/run_experiments.py')
experiments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiments)


class Proxy(threading.Thread):
    def __init__(self, server, delay, faults):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.server = server
        self.delay = delay
        self.faults = faults
        self.client = None
        self.done = threading.Event()
        self.counts = {}
        self.error = None

    def run(self):
        pending, serial = [], 0
        try:
            while not self.done.is_set():
                now = time.monotonic()
                while pending and pending[0][0] <= now:
                    _, _, wire, destination = heapq.heappop(pending)
                    self.sock.sendto(wire, destination)
                if not select.select([self.sock], [], [], .001)[0]:
                    continue
                wire, source = self.sock.recvfrom(4096)
                back = source == self.server
                if not back:
                    self.client = source
                destination = self.client if back else self.server
                kind, seq = wire[5], int.from_bytes(wire[16:20], 'big')
                key = back, kind, seq
                self.counts[key] = self.counts.get(key, 0) + 1
                if self.faults and self.counts[key] == 1 and (
                        (not back and kind == 3 and seq == 10) or
                        (back and kind in (4, 10) and seq in (5, 6, 7))):
                    continue
                serial += 1
                # Delay DATA and ACKs; keep control fixed to isolate DATA timers.
                delay = self.delay if kind in (3, 4, 10) else .002
                heapq.heappush(pending, (now + delay, serial, wire, destination))
        except Exception as exc:
            self.error = exc

    def close(self):
        self.done.set()
        if self.ident is not None:
            self.join(2)
        self.sock.close()
        if self.error:
            raise self.error


def trial(output, delay, faults, adaptive, sack, cc, repeat, size):
    name = f'delay{delay}-faults{int(faults)}-rto{adaptive}-sack{sack}-cc{cc}-{repeat}'
    directory = output / name
    directory.mkdir()
    source, target = directory / 'input.bin', directory / 'output.bin'
    source.write_bytes(bytes(range(256)) * (size // 256) + bytes(range(size % 256)))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    log = (directory / 'server.log').open('w')
    server = subprocess.Popen([str(ROOT / 'src/server'), str(port), str(target)], stdout=log,
                              stderr=subprocess.STDOUT,
                              env={**os.environ, 'RUDP_PROGRESS_LOG': str(directory / 'receiver.jsonl')})
    proxy = Proxy(('127.0.0.1', port), delay / 1000, faults)
    try:
        experiments.wait_until(lambda: 'Listening' in (directory / 'server.log').read_text(), 3, 'receiver', server)
        proxy.start()
        env = {**os.environ, 'RUDP_RTO': 'adaptive' if adaptive else 'fixed', 'RUDP_SACK': str(sack),
               'RUDP_CC': str(cc), 'RUDP_PROGRESS_LOG': str(directory / 'progress.jsonl')}
        result = subprocess.run([str(ROOT / 'src/client'), '127.0.0.1', str(proxy.sock.getsockname()[1]), str(source)],
                                env=env, capture_output=True, text=True, timeout=90)
        (directory / 'client.log').write_text(result.stdout + result.stderr)
        summary = experiments.parse_summary(result.stdout)
        input_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        output_hash = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        verified = input_hash == output_hash
        events = experiments.read_events(directory / 'progress.jsonl')
        row = dict(run_id=name, scenario='local-faults' if faults else 'local-delay', mode='localhost',
                   rto='adaptive' if adaptive else 'fixed', sack='bitmap' if sack else 'plain',
                   cc='on' if cc else 'off', loss_percent='deterministic' if faults else 0,
                   fail_after=0, flap_period=0, delay_ms=delay, repeat=repeat,
                   input_sha256=input_hash, output_sha256=output_hash,
                   success=result.returncode == 0 and verified, expectation_met=result.returncode == 0 and verified,
                   fast_retransmits=sum(e['event'] == 'retransmit' and e['reason'] == 'fast_gap' for e in events),
                   **summary)
        row['retransmit_fraction'] = summary.get('retransmits', 0) / max(1, summary.get('data_sends', 0))
        row['error'] = result.stderr.strip() if not row['success'] else ''
        return row
    finally:
        experiments.stop(server)
        log.close()
        proxy.close()
        source.unlink(missing_ok=True)
        target.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--delays', type=float, nargs='+', default=[5, 130])
    parser.add_argument('--size', type=int, default=65536)
    args = parser.parse_args()
    if args.repeats < 1 or args.size < 1 or any(d < 0 for d in args.delays):
        parser.error('repeats/size must be positive; delays nonnegative')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'environment.json').write_text(json.dumps(dict(source_sha256=experiments.source_fingerprint(),
        delays_ms=args.delays, repeats=args.repeats, size=args.size, clock='monotonic',
        scope='localhost deterministic proxy; not Mininet'), indent=2))
    rows = []
    for delay in args.delays:
        for faults in (False, True):
            # Baseline, RTO only, SACK only, both, then congestion-control ablation.
            for adaptive, sack, cc in ((0,0,0), (1,0,0), (0,1,0), (1,1,0), (1,1,1)):
                for repeat in range(args.repeats):
                    row = trial(args.output, delay, faults, adaptive, sack, cc, repeat, args.size)
                    rows.append(row)
                    experiments.write_metrics(args.output, rows)
                    print(row['run_id'], row.get('goodput_mbps'), row.get('retransmits'), row['success'], flush=True)
    return 0 if all(row['success'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
