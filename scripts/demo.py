#!/usr/bin/env python3
"""One-command Mininet demonstration: normal, netem, and link failover."""
import argparse
import csv
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'mininet'))
from topology import build_network


def events(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def progress(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # The client may still be appending this line.
        if event.get('event') == 'ack_progress':
            rows.append((event['monotonic_ns'] / 1e9, event['bytes']))
    return rows


def wait_ready(log, controller, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if controller.poll() is not None:
            raise RuntimeError('controller exited; inspect controller.log')
        if any(e['event'] == 'route_ready' for e in events(log)):
            return
        time.sleep(.05)
    raise RuntimeError('switches did not become ready; inspect controller.log')


def transfer(net, directory, source, scenario, mode):
    h1, h2 = net.get('h1', 'h2')
    output, trace = directory / 'received.bin', directory / 'progress.jsonl'
    server_log = open(directory / 'server.log', 'w')
    client_log = open(directory / 'client.log', 'w')
    server = h2.popen([str(ROOT / 'src/server'), '9000', str(output)],
                      stdout=server_log, stderr=subprocess.STDOUT)
    client = None
    failure = restored = None
    try:
        time.sleep(.15)
        env = dict(os.environ, RUDP_PROGRESS_LOG=str(trace))
        client = h1.popen([str(ROOT / 'src/client'), '10.0.0.2', '9000', str(source)],
                          env=env, stdout=client_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 45
        while client.poll() is None:
            now = time.monotonic()
            rows = progress(trace)
            if scenario == 'failure' and failure is None and rows and rows[-1][1] >= source.stat().st_size // 5:
                failure = now
                net.configLinkStatus('s1', 's2', 'down')
            # Both modes see exactly the same one-second outage. Static routing
            # resumes only when its original branch returns.
            if failure and restored is None and now - failure >= 1:
                net.configLinkStatus('s1', 's2', 'up')
                restored = time.monotonic()
            if now > deadline:
                raise RuntimeError('transfer exceeded 45 seconds')
            time.sleep(.01)
        if client.returncode:
            raise RuntimeError('client failed; inspect client.log')
        server.wait(timeout=12)
        if server.returncode:
            raise RuntimeError('server failed; inspect server.log')
    finally:
        if client and client.poll() is None:
            client.kill()
            client.wait()
        if server.poll() is None:
            server.kill()
            server.wait()
        server_log.close()
        client_log.close()
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(source) != digest(output):
        raise RuntimeError('SHA256 mismatch')
    stats = dict(re.findall(r'\b(bytes|retransmits|control_retransmits|seconds)=([0-9.]+)',
                            (directory / 'client.log').read_text()))
    if set(stats) != {'bytes', 'retransmits', 'control_retransmits', 'seconds'}:
        raise RuntimeError('missing client statistics')
    stats['retransmissions'] = str(int(stats.pop('retransmits')) + int(stats.pop('control_retransmits')))
    if scenario == 'failure' and failure is None:
        raise RuntimeError('transfer completed before link failure was triggered')
    ready = [e for e in events(directory / 'events.jsonl')
             if e['event'] == 'route_ready' and e.get('cause') == 'link_down'
             and e.get('path') == 'lower']
    route_seconds = (ready[0]['monotonic_ns'] / 1e9 - failure) if ready and failure else ''
    # Recovery is the first contiguous ACK advancement after the controller's
    # barrier-confirmed alternate route (or original-link restoration in static).
    recovery = ''
    if failure:
        threshold = ready[0]['monotonic_ns'] / 1e9 if ready else restored
        if threshold:
            samples = progress(trace)
            baseline = max((count for stamp, count in samples if stamp <= threshold), default=0)
            after = [stamp for stamp, count in samples if stamp > threshold and count > baseline]
            if after:
                recovery = after[0] - failure
    if scenario == 'failure' and mode == 'failover':
        if not ready or recovery == '' or recovery >= 1:
            raise RuntimeError('failover did not restore ACK progress before original-link restoration')
    output.unlink()  # Every received file was hashed; retain small diagnostic logs.
    return dict(scenario=scenario, mode=mode, **stats, recovery_seconds=recovery,
                route_seconds=route_seconds, sha256=digest(source))


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    measured = [p for folder in ('src', 'controller', 'mininet', 'scripts')
                for p in (ROOT / folder).rglob('*') if p.suffix in ('.c', '.h', '.py', '.sh')]
    fingerprint = hashlib.sha256(b''.join(p.relative_to(ROOT).as_posix().encode() + b'\0' + p.read_bytes() for p in sorted(measured))).hexdigest()
    (args.output / 'environment.json').write_text(json.dumps(dict(
        platform=platform.platform(), python=sys.version, source_sha256=fingerprint,
        mib=args.mib, repetitions=args.repetitions, datapath=args.datapath,
        controller='os-ken 2.11.2', bandwidth_mbps=10, interswitch_delay='5ms'), indent=2) + '\n')
    source = args.output / 'input.bin'
    source.write_bytes(os.urandom(args.mib * 1024 * 1024))
    cases = [('normal', 'failover'), ('netem', 'failover')]
    cases += [('failure', mode) for _ in range(args.repetitions) for mode in ('static', 'failover')]
    fields = ['scenario', 'mode', 'bytes', 'retransmissions', 'seconds',
              'recovery_seconds', 'route_seconds', 'sha256']
    with open(args.output / 'metrics.csv', 'w', newline='') as result:
        writer = csv.DictWriter(result, fieldnames=fields)
        writer.writeheader()
        for index, (scenario, mode) in enumerate(cases, 1):
            directory = args.output / ('%02d-%s-%s' % (index, scenario, mode))
            directory.mkdir()
            log = open(directory / 'controller.log', 'w')
            env = dict(os.environ, RUDP_MODE=mode, RUDP_EVENT_LOG=str(directory / 'events.jsonl'))
            controller = subprocess.Popen([str(Path(sys.executable).with_name('osken-manager')), '--ofp-tcp-listen-port', '6653',
                                           str(ROOT / 'controller/failover.py')], env=env,
                                          stdout=log, stderr=subprocess.STDOUT)
            net = build_network(datapath=args.datapath)
            try:
                net.start()
                wait_ready(directory / 'events.jsonl', controller)
                if scenario == 'netem':
                    # Real Linux netem, in both directions; no UDP proxy.
                    for host in net.hosts:
                        command = 'tc qdisc replace dev %s root netem delay 8ms 2ms loss 2%% duplicate 1%% reorder 20%% 50%%' % host.defaultIntf()
                        response = host.cmd(command)
                        if response.strip():
                            raise RuntimeError(response)
                with open(directory / 'flows.txt', 'w') as flows:
                    for switch in net.switches:
                        flows.write(switch.cmd('ovs-ofctl -O OpenFlow13 dump-flows ' + switch.name))
                (directory / 'qdisc.txt').write_text(''.join(host.cmd('tc -s qdisc show') for host in net.hosts))
                row = transfer(net, directory, source, scenario, mode)
                with open(directory / 'flows-after.txt', 'w') as flows:
                    for switch in net.switches:
                        flows.write(switch.cmd('ovs-ofctl -O OpenFlow13 dump-flows ' + switch.name))
                writer.writerow(row)
                result.flush()
                print('%s/%s: %s bytes, %ss, %s retransmissions, recovery=%s; SHA256 OK' %
                      (scenario, mode, row['bytes'], row['seconds'], row['retransmissions'], row['recovery_seconds']), flush=True)
            finally:
                net.stop()
                controller.terminate()
                try:
                    controller.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    controller.kill()
                    controller.wait()
                log.close()
    print('Results:', args.output / 'metrics.csv')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / time.strftime('demo-%Y%m%d-%H%M%S'))
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--mib', type=int, default=2)
    parser.add_argument('--datapath', choices=['kernel', 'user'], default='user')
    args = parser.parse_args()
    args.output = args.output.resolve()
    if os.geteuid() != 0:
        parser.error('run as root (or use Docker Compose)')
    if args.mib < 1 or args.repetitions < 1:
        parser.error('mib and repetitions must be positive')
    run(args)
