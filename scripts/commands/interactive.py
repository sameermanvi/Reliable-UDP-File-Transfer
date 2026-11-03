"""Single-key assessment menu using real protocol binaries and retained measurements."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import zlib

ROOT = Path(__file__).resolve().parents[2]
STAGES = (
    "Protocol Framing, 24-Byte Header & Baseline C Transfer (0% Loss)",
    "Selective Repeat (32-Slot), SACK Bitmap & Adaptive RTO (10% Loss)",
    "Concurrent Multi-Port Transfers & Session Isolation (2 Flows)",
    "Mininet 4-Switch Diamond & OpenFlow 1.3 Hard Link Failover",
    "SDN Soft Degradation, Adaptive Probe Scheduling & Multipath",
    "Performance Comparison (Static Failure vs. Failover & SACK Matrix)",
    "Full Automated Test Suite Verification (Protocol + SDN + Multipath)",
    "Launch Live Browser Telemetry Dashboard (http://localhost:8080)",
)


def run(command, **kwargs):
    print("$ " + " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True, **kwargs)


def summary(lines, ok=True):
    color = ('\033[32m' if ok else '\033[31m') if sys.stdout.isatty() else ''
    reset = '\033[0m' if color else ''
    print(color + "\n+-- EXAMINER SUMMARY — WHAT THIS PROVED --+")
    for line in lines:
        print("| " + str(line))
    print("+----------------------------------------+" + reset, flush=True)


def output_dir(name):
    path = ROOT/'results'/name
    if path.exists():
        path = path.with_name(name + '-' + str(time.time_ns()))
    path.mkdir(parents=True)
    return path


def pump(process, label, lines, ready):
    for line in process.stdout:
        print("[" + label + "] " + line.rstrip(), flush=True)
        lines.append(line)
        if line.startswith("Listening on UDP port"):
            ready.set()


def stop(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def localhost(directory, configurations, ports):
    """Start all bound receivers before starting any clients."""
    servers, clients, threads, rows = [], [], [], []
    try:
        for index, (flags, port) in enumerate(zip(configurations, ports)):
            source = directory/('sample.bin' if len(ports)==1 else f'sample_flow{index+1}.bin')
            if not source.exists():
                source.write_bytes(os.urandom(1024*1024))
            target = directory/f'out_flow{index+1}.bin'
            trace = directory/f'progress-{index}.jsonl'
            server_lines, client_lines, ready = [], [], threading.Event()
            receiver = subprocess.Popen([str(ROOT/'server'), str(port), str(target)],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        env=dict(os.environ, RUDP_PROGRESS_LOG=str(directory/f'receiver-{index}.jsonl')))
            servers.append(receiver)
            thread = threading.Thread(target=pump, args=(receiver, f'server:{port}', server_lines, ready), daemon=True)
            thread.start()
            threads.append(thread)
            if not ready.wait(3):
                raise RuntimeError(f'Receiver on port {port} did not bind. Check port availability.')
            rows.append(dict(source=source, target=target, trace=trace, flags=flags,
                             server_lines=server_lines, client_lines=client_lines))
        for index, row in enumerate(rows):
            env = dict(os.environ, RUDP_PROGRESS_LOG=str(row['trace']))
            client = subprocess.Popen([str(ROOT/'client'), '--host', '127.0.0.1', '--port',
                                       str(ports[index]), '--file', str(row['source']), *row['flags']],
                                      env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            clients.append(client)
            thread = threading.Thread(target=pump, args=(client, f'client:{ports[index]}',
                                                        row['client_lines'], threading.Event()), daemon=True)
            thread.start()
            threads.append(thread)
        deadline = time.monotonic()+180
        while any(p.poll() is None for p in [*clients, *servers]):
            if any(p.poll() not in (None, 0) for p in [*clients, *servers]):
                raise RuntimeError('An endpoint failed. See its output above.')
            if time.monotonic()>deadline:
                raise RuntimeError('Transfer exceeded 180 seconds')
            time.sleep(.05)
        for thread in threads:
            thread.join(2)
        for row in rows:
            sender = dict(re.findall(r'(\w+)=([^\s]+)', ''.join(row['client_lines'])))
            receiver = dict(re.findall(r'(\w+)=([^\s]+)', ''.join(row['server_lines'])))
            original, received = row['source'].read_bytes(), row['target'].read_bytes()
            digest = hashlib.sha256(original).hexdigest()
            output_hash = hashlib.sha256(received).hexdigest()
            crc = f'{zlib.crc32(original):08x}'
            if digest != output_hash or sender.get('crc32') != crc or receiver.get('crc32') != crc:
                raise RuntimeError('CRC32 or SHA-256 mismatch')
            ids = {r['transfer_id'] for r in map(json.loads, row['trace'].read_text().splitlines())
                   if 'transfer_id' in r}
            if len(ids)!=1:
                raise RuntimeError('Expected one transfer ID per sender')
            row['metrics'] = dict(sender, out_of_order=receiver.get('out_of_order'),
                                  duplicates=receiver.get('duplicates'), sha256_match=True,
                                  transfer_id=ids.pop(), source_sha256=digest, output_sha256=output_hash)
            checksum = shutil.which('sha256sum')
            if checksum:
                run([checksum, str(row['source']), str(row['target'])])
            else:
                print("SHA-256 " + digest + "  " + str(row['source']))
                print("SHA-256 " + output_hash + "  " + str(row['target']))
        result = [r['metrics'] for r in rows]
        (directory/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
        return result
    finally:
        for process in [*clients, *servers]:
            stop(process)
        for thread in threads:
            thread.join(2)
        for process in [*clients, *servers]:
            process.stdout.close()


def comparison(rows):
    columns = ('seconds', 'goodput_mbps', 'data_sends', 'retransmits', 'out_of_order', 'duplicates', 'sha256_match')
    print("\nMetric                  " + " | ".join(f"Run {i+1:>2}" for i in range(len(rows))))
    for key in columns:
        print(f"{key:<23} " + " | ".join(str(r.get(key, 'N/A')).rjust(12) for r in rows))


def network_backend():
    python = ROOT/'.venv/bin/python'
    python = str(python) if python.exists() else sys.executable
    native = (shutil.which('ovs-vsctl') and
              subprocess.run([python, '-c', 'import mininet, os_ken'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0)
    if native:
        prefix = [] if os.geteuid()==0 else ['sudo']
        if subprocess.run([*prefix, 'ovs-vsctl', 'show'], stdout=subprocess.DEVNULL).returncode == 0:
            return [*prefix, python, 'scripts/run.py'], False
    if shutil.which('docker'):
        docker = ['docker']
        if subprocess.run([*docker, 'info'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            if sys.platform.startswith('linux') and sys.stdin.isatty():
                docker = ['sudo', 'docker']
            if subprocess.run([*docker, 'info'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                return None
        # Rebuild against this checkout so an older demo image cannot hide new code.
        run([*docker, 'build', '-t', 'rudp-lab', '.'])
        return [*docker, 'run', '--rm', '--privileged', '-v', str(ROOT/'results')+':/project/results',
                '-e', 'RUDP_MULTIPATH=1', 'rudp-lab', 'python3', 'scripts/run.py'], True
    return None


def open_plot(directory, pattern):
    plots = sorted(directory.rglob(pattern))
    if not plots:
        print("No " + pattern + " plot was generated.")
        return
    print("Plot: " + str(plots[0]))
    opener = shutil.which('open') if sys.platform=='darwin' else shutil.which('xdg-open')
    if opener and (sys.platform=='darwin' or os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        subprocess.Popen([opener, str(plots[0])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def sdn(soft=False, backend=None):
    print("h1 -- s1 -- { s2 Upper / s3 Lower } -- s4 -- h2")
    backend = backend or network_backend()
    if not backend:
        raise RuntimeError('Start Docker Engine or prepare native Mininet/OVS.')
    prefix, docker = backend
    directory = output_dir('live-soft' if soft else 'live-failover')
    command = prefix + ['demo', '--mode', 'failover', '--datapath', 'user',
                        '--output', str(directory.relative_to(ROOT))]
    if soft:
        command += ['--scenario', 'soft-degradation', '--mib', '16']
    env = dict(os.environ, RUDP_MULTIPATH='1')
    run(command, env=env)
    with (directory/'metrics.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    if not rows or any(r['success']!='True' or r['sha256_match']!='True' or r['expectation_met']!='True' for r in rows):
        raise RuntimeError('Network trial did not satisfy transfer expectations')
    intervals, health, ready = [], [], []
    for path in directory.rglob('controller.jsonl'):
        for record in map(json.loads, path.read_text().splitlines()):
            if record['event']=='probe_schedule':
                intervals.append(record['interval_seconds'])
            if record['event']=='path_health':
                health.append(record)
            if record['event']=='route_ready':
                ready.append(record)
    recovery = [r.get('link_down_to_progress_seconds') for r in rows
                if r.get('link_down_to_progress_seconds') not in ('', None)]
    summary([f"Transfers {len(rows)} | CRC32 & SHA-256 MATCH",
             "Link-down to useful ACK (ms): " + ', '.join(f'{float(t)*1000:.3f}' for t in recovery) if recovery else "Soft route readiness: " + ', '.join(str(r.get('path')) for r in ready),
             f"Probe intervals observed: {min(intervals):.3f}–{max(intervals):.3f}s" if intervals else "Probe interval records unavailable"])
    if soft and health:
        print("Last recorded directional samples and scores:")
        print(json.dumps(health[-1], indent=2))
    open_plot(directory, 'timeline.svg')


def retained():
    paths = [ROOT/'results/rubric-final'/part/'metrics.csv' for part in ('matrix','lower-recovery','robustness')]
    rows = []
    for path in paths:
        with path.open() as stream:
            rows.extend(csv.DictReader(stream))
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['file_bytes'], row['scenario'], row['mode'], row['rto'], row['sack'], row['cc'])].append(row)
    print("RETAINED EVALUATION — measured earlier implementation; no new matrix run")
    print("Bytes      Scenario          Mode     RTO       SACK      CC    Trials Success Expected Mean Mb/s")
    for key, group in sorted(grouped.items()):
        size, scenario, mode, rto, sack, cc = key
        goodput = [float(r['goodput_mbps']) for r in group if r['goodput_mbps']]
        mean = f'{sum(goodput)/len(goodput):.3f}' if goodput else 'N/A'
        print(f'{size:<10} {scenario:<17} {mode:<8} {rto:<9} {sack:<9} {cc:<5} {len(group):>5} {sum(r["success"]=="True" for r in group):>7} {sum(r["expectation_met"]=="True" for r in group):>8} {mean:>9}')
    success = sum(r['success']=='True' and r['sha256_match']=='True' for r in rows)
    failures = sum(r['mode']=='static' and r['success']=='False' and r['expectation_met']=='True' for r in rows)
    if len(rows)!=180 or success!=132 or failures!=48:
        raise RuntimeError('Retained evidence counts differ from the documented evaluation')
    summary([f"{len(rows)} recorded outcomes | {success} hash-matched successes",
             f"{failures} expected static-route failures | all expectations met",
             "Successful outcomes include normal, loss and recovery transfers."])
    sample = next(r for r in rows if r['mode']=='static' and r['success']=='False')
    print("Recorded static failure: " + json.dumps({k:sample[k] for k in ('success','expectation_met','retransmits','error')}))
    print("MAX_RETRIES=30 bounds retries per DATA slot; total retries include multiple slots.")
    open_plot(ROOT/'results/rubric-final', 'goodput_mbps.svg')


def stage(number):
    if number in (1,2,3):
        run(['make'])
    if number==1:
        print("Wire v1 (network byte order): 0..3 magic | 4 version | 5 encoded type/flags")
        print("6..7 length u16 | 8..15 transfer_id u64 | 16..19 sequence u32 | 20..23 CRC32")
        print("Logical flags: SACK_CAPABLE=1 | SACK_BITMAP_PRESENT=2 | CONTROL_REPLY=4")
        print("Logical flags share the type encoding at byte 5. PAYLOAD_SIZE=1024 | WINDOW_SIZE=32")
        rows = localhost(output_dir('stage1'), [['--drop-rate','0']], [9000])
        comparison(rows)
        summary([f"Bytes {rows[0]['bytes']} | Packets {rows[0]['packets']}",
                 f"Retransmits {rows[0]['retransmits']} | Goodput {rows[0]['goodput_mbps']} Mb/s",
                 "CRC32 & SHA-256 MATCH"])
    elif number==2:
        directory = output_dir('stage2')
        rows = []
        sample = os.urandom(1024*1024)
        for name, flags in [('baseline',['--no-sack','--fixed-rto','--no-cc']),
                            ('adaptive',['--sack','--adaptive-rto','--cc'])]:
            child = directory/name
            child.mkdir()
            (child/'sample.bin').write_bytes(sample)
            rows += localhost(child, [flags+['--drop-rate','0.10']], [9000])
        comparison(rows)
        summary(["A/B uses independently sampled 10% DATA loss",
                 "Reported metrics are from the two executions above",
                 "Both CRC32 & SHA-256 MATCH"])
    elif number==3:
        rows = localhost(output_dir('stage3'), [['--drop-rate','0.05','--sack','--adaptive-rto','--cc']]*2, [9000,9001])
        if rows[0]['transfer_id']==rows[1]['transfer_id'] or rows[0]['source_sha256']==rows[1]['source_sha256']:
            raise RuntimeError('Distinct session/source validation failed')
        comparison(rows)
        summary([f"Flow 9000 | ID {rows[0]['transfer_id']} | {rows[0]['goodput_mbps']} Mb/s",
                 f"Flow 9001 | ID {rows[1]['transfer_id']} | {rows[1]['goodput_mbps']} Mb/s",
                 "Distinct payloads and sessions | Both SHA-256 MATCH"])
    elif number==4:
        sdn()
    elif number==5:
        for name in ('test_probe_schedule.py','test_multipath.py','test_probes.py'):
            run([sys.executable, 'tests/'+name])
        print("Probe policy: healthy spacing grows to 1.5s, loss halves it to 0.1s minimum.")
        print("Directional EWMA weight 0.25; score=max(loss+min(delay_ms,500)/1000).")
        print("Health improvement >0.02 and 2s hold-down govern soft route moves.")
        print("The client weights DATA by sequence/DSCP; multipath.py filters eligible branches.")
        backend = network_backend()
        if backend:
            sdn(soft=True, backend=backend)
        else:
            summary(["Probe, scheduling and multipath tests passed",
                     "Live Mininet trial unavailable until Docker/native OVS is running",
                     "Live control-plane metrics remain unmeasured in this step"])
    elif number==6:
        retained()
    elif number==7:
        process = subprocess.Popen(['make','test'], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        lines = []
        try:
            for line in process.stdout:
                print(line, end='', flush=True)
                lines.append(line)
            if process.wait():
                raise RuntimeError('Test suite failed')
        finally:
            stop(process)
            process.stdout.close()
        count = sum(map(int, re.findall(r'Ran (\d+) tests?', ''.join(lines))))
        summary([f"{count} tests passed", "Protocol, transport, probes, SDN, multipath and HTTP telemetry",
                 "Process exit status 0"])
    elif number==8:
        run([sys.executable,'scripts/run.py','viz','--port','8080'])


def read_key():
    if not sys.stdin.isatty():
        return sys.stdin.readline().strip().lower()
    if os.name=='nt':
        import msvcrt
        return msvcrt.getwch().lower()
    import termios
    import tty
    settings = termios.tcgetattr(sys.stdin.fileno())
    try:
        tty.setcbreak(sys.stdin.fileno())
        return sys.stdin.read(1).lower()
    finally:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, settings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step', choices=[str(i) for i in range(1,9)]+['a'])
    args = parser.parse_args()
    while True:
        if args.step:
            key = args.step
        else:
            print("\n" + "="*80 + "\n  RELIABLE UDP + OPENFLOW 1.3 SDN — INTERACTIVE ASSESSMENT CONSOLE\n" + "="*80)
            for index, title in enumerate(STAGES, 1):
                print(f"  [{index}] Stage {index}: {title}")
            print("  [a] Run Stages 1 -> 6 Sequentially\n  [q] Quit\n" + "="*80)
            print("Select stage [1-8, a, q]: ", end='', flush=True)
            try:
                key = read_key()
            except KeyboardInterrupt:
                print()
                return 130
            print(key)
        if key in ('q',''):
            return 0
        if key not in '12345678a' or len(key)!=1:
            continue
        try:
            for number in range(1,7) if key=='a' else [int(key)]:
                stage(number)
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
            summary(["Stage failed", str(exc), "See actual endpoint/command output above"], ok=False)
            if args.step:
                return 1
        except KeyboardInterrupt:
            print("\nStage interrupted.")
            if args.step:
                return 130
        if args.step:
            return 0


if __name__=='__main__':
    raise SystemExit(main())
