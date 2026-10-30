#!/usr/bin/env python3
"""Run reproducible UDP transfers over a real Mininet/OpenFlow diamond."""

import argparse
import csv
import hashlib
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def monotonic_ns():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def source_fingerprint():
    """Identify measured code even when Docker excludes Git metadata."""
    checksum = hashlib.sha256()
    files = [path for folder in ("src", "controller", "mininet", "scripts")
             for path in (ROOT / folder).rglob("*")
             if path.is_file() and path.suffix in (".c", ".h", ".py", ".sh")]
    files += [ROOT / "src/Makefile", ROOT / "requirements-sdn.txt", ROOT / "Dockerfile"]
    for path in sorted(files):
        checksum.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes() + b"\0")
    return checksum.hexdigest()


def read_events(path):
    """Allow an incomplete final line while another process is appending."""
    if not Path(path).exists():
        return []
    events = []
    for line in Path(path).read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def parse_summary(text):
    lines = [line for line in text.splitlines() if line.startswith("Transfer complete:")]
    if not lines:
        return {}
    result = {}
    for key, value in re.findall(r"(\w+)=([^\s]+)", lines[-1]):
        if key == "crc32":
            result[key] = value
        elif key in ("seconds", "goodput_mbps"):
            result[key] = float(value)
        else:
            result[key] = int(value)
    return result


def recovery_metrics(progress, controller_events, failure_ns):
    """Recovery is new contiguous ACK progress after lower-path barriers finish."""
    result = dict(route_install_seconds=None, progress_recovery_seconds=None,
                  ack_gap_seconds=None)
    if failure_ns is None:
        return result
    routes = [event for event in controller_events
              if event.get("event") == "route_ready" and event.get("path") == "lower"
              and event.get("monotonic_ns", 0) >= failure_ns]
    if not routes:
        return result
    ready = min(event["monotonic_ns"] for event in routes)
    result["route_install_seconds"] = (ready - failure_ns) / 1e9
    advances = [event for event in progress if event.get("event") == "ack_progress"]
    before = [event for event in advances if event["monotonic_ns"] < failure_ns]
    prior_base = max((event["base"] for event in advances
                      if event["monotonic_ns"] < ready), default=0)
    after = [event for event in advances
             if event["monotonic_ns"] >= ready and event["base"] > prior_base]
    if after:
        resumed = min(event["monotonic_ns"] for event in after)
        result["progress_recovery_seconds"] = (resumed - failure_ns) / 1e9
        if before:
            result["ack_gap_seconds"] = (resumed - max(
                event["monotonic_ns"] for event in before)) / 1e9
    return result


def digest(path):
    if not path.exists():
        return None
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def wait_until(predicate, timeout, description, process=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        if process is not None and process.poll() is not None:
            raise RuntimeError(description + ": process exited")
        time.sleep(0.02)
    raise RuntimeError("Timed out waiting for " + description)


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_topology():
    return load_module(ROOT / "mininet/topology.py", "lab_topology")


def save_network_state(network, directory, label):
    sections = []
    for switch in network.switches:
        sections.append(f"Switch {switch.name}\n" + switch.cmd(
            "ovs-ofctl -O OpenFlow13 dump-flows", switch.name))
        for interface in switch.intfList():
            if interface.name != "lo":
                sections.append(f"Interface {interface.name}\n" + switch.cmd(
                    "tc -s qdisc show dev", interface.name))
    for host in network.hosts:
        sections.append(f"Host {host.name} protocol counters\n" + host.cmd("cat /proc/net/snmp"))
    (directory / f"network-{label}.txt").write_text("\n".join(sections))


def run_trial(args, topology, scenario, mode, repeat, source, source_hash):
    trial_id = f"{scenario}-{mode}-{repeat:02d}"
    directory = args.output / trial_id
    directory.mkdir()
    controller_events = directory / "controller.jsonl"
    controller = None
    network = None
    handles, clients, servers, outputs, progress_files = [], [], [], [], []
    failure_ns = None
    failure_end_ns = None
    error = ""
    loss = args.loss if scenario == "loss" else 0
    try:
        controller_log = (directory / "controller.log").open("w")
        handles.append(controller_log)
        env = os.environ.copy()
        env.update(RUDP_MODE=mode, RUDP_EVENT_LOG=str(controller_events))
        port = free_port()
        manager = Path(sys.executable).parent / "osken-manager"
        command = [str(manager), "--ofp-tcp-listen-port", str(port),
                   str(ROOT / "controller/failover.py")]
        controller = subprocess.Popen(command, cwd=ROOT, env=env,
                                      stdout=controller_log, stderr=subprocess.STDOUT)
        # Listen readiness is checked before OVS starts its reconnect loop.
        def listening():
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return True
            except OSError:
                return False
        wait_until(listening, 15, "controller listening", controller)
        # Verify the initial network before injecting loss. A deliberately lost
        # ping must not be misclassified as an infrastructure failure.
        network = topology.build_network(controller_port=port, bandwidth=args.bandwidth,
                                         delay=args.delay, loss=0, datapath=args.datapath)
        network.start()
        wait_until(lambda: any(e.get("event") == "route_ready" and e.get("path") == "upper"
                               for e in read_events(controller_events)),
                   20, "initial upper path", controller)
        h1, h2 = network.get("h1", "h2")
        ping = h1.popen(["ping", "-c", "1", "-W", "3", h2.IP()],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        ping_output, _ = ping.communicate(timeout=5)
        (directory / "connectivity.log").write_bytes(ping_output)
        if ping.returncode:
            raise RuntimeError("Initial host connectivity failed")
        if loss:
            impairments = load_module(ROOT / "mininet/link_impairment.py", "lab_impairment")
            for first, second in (("s1", "s2"), ("s2", "s4"), ("s1", "s3"), ("s3", "s4")):
                impairments.set_link_loss(network, first, second, loss)
        save_network_state(network, directory, "initial")
        for flow in range(args.flows):
            output = directory / f"received-{flow}.bin"
            outputs.append(output)
            progress_files.append(directory / f"progress-{flow}.jsonl")
            server_log = (directory / f"server-{flow}.log").open("w")
            handles.append(server_log)
            server = h2.popen([str(ROOT / "src/server"), str(9000 + flow), str(output)],
                              stdout=server_log, stderr=subprocess.STDOUT)
            servers.append(server)
            wait_until(lambda f=flow: "Listening on UDP port" in
                       (directory / f"server-{f}.log").read_text(),
                       3, "UDP receiver", server)
        for flow in range(args.flows):
            client_log = (directory / f"client-{flow}.log").open("w")
            handles.append(client_log)
            client_env = os.environ.copy()
            client_env["RUDP_PROGRESS_LOG"] = str(progress_files[flow])
            clients.append(h1.popen([str(ROOT / "src/client"), h2.IP(), str(9000 + flow),
                                     str(source)], env=client_env,
                                    stdout=client_log, stderr=subprocess.STDOUT))
        deadline = time.monotonic() + args.timeout
        first_progress_ns = None
        while any(client.poll() is None for client in clients):
            if controller.poll() is not None:
                raise RuntimeError("Controller exited during transfer")
            if time.monotonic() > deadline:
                raise RuntimeError("Transfer deadline exceeded")
            if scenario == "link-failure" and failure_ns is None:
                events = [read_events(path) for path in progress_files]
                started = [[e for e in flow if e.get("event") == "ack_progress"
                            and e.get("base", 0) > 0] for flow in events]
                if all(started):
                    if first_progress_ns is None:
                        first_progress_ns = max(flow[0]["monotonic_ns"] for flow in started)
                    if monotonic_ns() - first_progress_ns >= args.fail_after * 1e9:
                        if any(client.poll() is not None for client in clients):
                            raise RuntimeError("Transfer ended before failure; increase --file-size")
                        failure_ns = monotonic_ns()
                        network.configLinkStatus("s1", "s2", "down")
                        failure_end_ns = monotonic_ns()
            time.sleep(0.02)
        if scenario == "link-failure" and failure_ns is None:
            raise RuntimeError("No failure injected; increase --file-size or reduce --fail-after")
        for server in servers:
            server.wait(timeout=12)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        error = str(exc)
    finally:
        for process in clients + servers:
            stop(process)
        if network is not None:
            try:
                save_network_state(network, directory, "final")
                network.stop()
            except Exception as exc:
                error = error or f"Network cleanup failed: {exc}"
        stop(controller)
        for handle in handles:
            handle.close()
    events = read_events(controller_events)
    rows = []
    for flow in range(args.flows):
        client_path = directory / f"client-{flow}.log"
        server_path = directory / f"server-{flow}.log"
        client_text = client_path.read_text() if client_path.exists() else ""
        server_text = server_path.read_text() if server_path.exists() else ""
        sent = parse_summary(client_text)
        received = parse_summary(server_text)
        output = directory / f"received-{flow}.bin"
        output_hash = digest(output)
        client_exit = clients[flow].returncode if flow < len(clients) else None
        server_exit = servers[flow].returncode if flow < len(servers) else None
        success = (not error and client_exit == 0 and server_exit == 0
                   and output_hash == source_hash and output.stat().st_size == args.file_size)
        expected = not (scenario == "link-failure" and mode == "static")
        recovery = recovery_metrics(read_events(directory / f"progress-{flow}.jsonl"),
                                    events, failure_ns)
        intervention_ok = (scenario != "link-failure" or failure_ns is not None)
        if scenario == "link-failure" and mode == "failover":
            intervention_ok = intervention_ok and recovery["progress_recovery_seconds"] is not None
        if not expected:
            intervention_ok = (intervention_ok and client_exit not in (None, 0)
                               and server_exit not in (None, 0)
                               and "Retry limit reached for DATA" in client_text
                               and "transfer incomplete" in server_text
                               and not output.exists())
        # An infrastructure exception never counts as the expected static failure.
        expectation_met = not error and intervention_ok and success == expected
        row = dict(run_id=trial_id, scenario=scenario, mode=mode, repeat=repeat,
                   flow_id=flow, flow_count=args.flows, file_bytes=args.file_size,
                   bandwidth_mbps=args.bandwidth, delay=args.delay, loss_percent=loss,
                   client_exit=client_exit, server_exit=server_exit,
                   sha256_match=output_hash == source_hash, success=success,
                   expected_success=expected, expectation_met=bool(expectation_met),
                   seconds=sent.get("seconds"), goodput_mbps=sent.get("goodput_mbps"),
                   data_packets=sent.get("packets"), data_sends=sent.get("data_sends"),
                   retransmits=sent.get("retransmits"),
                   control_retransmits=sent.get("control_retransmits"),
                   duplicates=received.get("duplicates"), out_of_order=received.get("out_of_order"),
                   failure_monotonic_ns=failure_ns, failure_command_end_ns=failure_end_ns,
                   input_sha256=source_hash, output_sha256=output_hash, error=error,
                   **recovery)
        rows.append(row)
        if output.exists() and not args.keep_files:
            output.unlink()
    (directory / "metrics.json").write_text(json.dumps(rows, indent=2) + "\n")
    return rows


def write_metrics(output, rows):
    (output / "metrics.json").write_text(json.dumps(rows, indent=2) + "\n")
    if rows:
        with (output / "metrics.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", nargs="+", choices=["normal", "loss", "link-failure"],
                        default=["normal", "loss", "link-failure"])
    parser.add_argument("--modes", nargs="+", choices=["static", "failover"], default=["static", "failover"])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--flows", type=int, default=1)
    parser.add_argument("--file-size", type=int, default=4 * 1024 * 1024)
    parser.add_argument("--bandwidth", type=float, default=10)
    parser.add_argument("--delay", default="5ms")
    parser.add_argument("--loss", type=float, default=2)
    parser.add_argument("--fail-after", type=float, default=1,
                        help="seconds after every flow has made ACK progress")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--datapath", choices=["kernel", "user"], default="kernel")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results" / time.strftime("run-%Y%m%d-%H%M%S"))
    parser.add_argument("--keep-files", action="store_true")
    args = parser.parse_args()
    if (args.repeats < 1 or not 1 <= args.flows <= 16 or args.file_size < 1
            or args.bandwidth <= 0 or not 0 <= args.loss <= 100
            or args.fail_after < 0 or args.timeout <= 0):
        parser.error("Invalid repeat/flow/file-size/bandwidth/loss/timing value")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:ms|us|s)", args.delay):
        parser.error("--delay must be a nonnegative duration such as 5ms")
    args.output = args.output.resolve()
    return args


def main():
    args = arguments()
    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Experiments require root on Linux (Mininet network namespaces).")
    for command in ("ovs-vsctl", "tc", "ping", "ethtool"):
        if shutil.which(command) is None:
            raise SystemExit(f"Missing {command}; run scripts/setup_env.sh first")
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Output directory is not empty; choose a fresh --output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    subprocess.run(["make", "-C", str(ROOT / "src")], check=True)
    topology = load_topology()
    config = vars(args).copy()
    config["output"] = str(args.output)
    config.update(python=sys.version, platform=platform.platform(),
                  controller="os-ken " + importlib.metadata.version("os-ken"),
                  source_sha256=source_fingerprint(), file_random_seed=243,
                  ovs_version=subprocess.check_output(["ovs-vsctl", "--version"], text=True).strip(),
                  generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    (args.output / "environment.json").write_text(json.dumps(config, indent=2) + "\n")
    source = args.output / "input.bin"
    rng = random.Random(243)
    remaining = args.file_size
    with source.open("wb") as stream:
        while remaining:
            size = min(65536, remaining)
            stream.write(rng.randbytes(size))
            remaining -= size
    source_hash = digest(source)
    rows = []
    try:
        for scenario in args.scenarios:
            for repeat in range(1, args.repeats + 1):
                for mode in args.modes:
                    print(f"Running {scenario}, {mode}, repetition {repeat}", flush=True)
                    trial = run_trial(args, topology, scenario, mode, repeat, source, source_hash)
                    rows.extend(trial)
                    write_metrics(args.output, rows)
                    for row in trial:
                        status = "PASS" if row["expectation_met"] else "FAIL"
                        print(f"  {status} flow={row['flow_id']} success={row['success']} "
                              f"goodput={row['goodput_mbps']} error={row['error']}", flush=True)
    finally:
        if source.exists() and not args.keep_files:
            source.unlink()
    print(f"Results: {args.output / 'metrics.csv'}")
    return 0 if rows and all(row["expectation_met"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
