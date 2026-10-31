#!/usr/bin/env python3
"""Run reproducible UDP transfers over a real Mininet/OpenFlow diamond."""

import argparse
import itertools
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


def recovery_metrics(progress, controller_events, failure_ns, failure_path="upper"):
    """New contiguous ACK advancement after barriers on the surviving branch.

    Inputs must be bounded at the next intervention by the caller for repeated
    faults. No route/progress observation is censored, never zero latency.
    """
    result = dict(route_install_seconds=None, progress_recovery_seconds=None,
                  ack_gap_seconds=None, link_detection_seconds=None,
                  link_down_to_progress_seconds=None, route_to_progress_seconds=None,
                  failure_monotonic_ns=failure_ns, link_down_monotonic_ns=None,
                  route_ready_monotonic_ns=None, useful_ack_monotonic_ns=None,
                  recovery_status="not_applicable" if failure_ns is None else "censored_no_route")
    if failure_ns is None:
        return result
    expected = "lower" if failure_path == "upper" else "upper"
    ports = {"upper": {(1, 2), (2, 1), (2, 2), (4, 1)},
             "lower": {(1, 3), (3, 1), (3, 2), (4, 2)}}
    downs = [e["monotonic_ns"] for e in controller_events
             if e.get("event") == "link_down" and e.get("monotonic_ns", 0) >= failure_ns
             and ("dpid" not in e or (e["dpid"], e.get("port")) in ports[failure_path])]
    observed = min(downs) if downs else None
    if observed is not None:
        result["link_down_monotonic_ns"] = observed
        result["link_detection_seconds"] = (observed - failure_ns) / 1e9
    routes = [e for e in controller_events if e.get("event") == "route_ready"
              and e.get("path") == expected and e.get("monotonic_ns", 0) >= failure_ns
              and e.get("cause") not in ("startup", "link_up")
              and (observed is None or e["monotonic_ns"] >= observed)]
    if not routes:
        return result
    ready = min(e["monotonic_ns"] for e in routes)
    result.update(route_install_seconds=(ready - failure_ns) / 1e9,
                  route_ready_monotonic_ns=ready, recovery_status="censored_no_progress")
    advances = sorted((e for e in progress if e.get("event") == "ack_progress"),
                      key=lambda e: e["monotonic_ns"])
    before = [e for e in advances if e["monotonic_ns"] < failure_ns]
    prior_base = max((e["base"] for e in advances if e["monotonic_ns"] <= ready), default=0)
    after = [e for e in advances if e["monotonic_ns"] > ready and e["base"] > prior_base]
    if after:
        resumed = after[0]["monotonic_ns"]
        result.update(progress_recovery_seconds=(resumed - failure_ns) / 1e9,
                      route_to_progress_seconds=(resumed - ready) / 1e9,
                      useful_ack_monotonic_ns=resumed, recovery_status="recovered")
        if observed is not None:
            result["link_down_to_progress_seconds"] = (resumed - observed) / 1e9
        if before:
            result["ack_gap_seconds"] = (resumed - before[-1]["monotonic_ns"]) / 1e9
    return result


def outage_metrics(progress, controller_events, interventions):
    """Bound each failure by the next intervention; distinguish inactive-path flaps."""
    records = []
    for index, intervention in enumerate(interventions):
        if intervention["event"] != "failure_injected":
            continue
        stamp = intervention["monotonic_ns"]
        failed_path = intervention.get("path", "upper")
        end = interventions[index + 1]["monotonic_ns"] if index + 1 < len(interventions) else float("inf")
        prior = [e for e in controller_events if e.get("event") == "route_ready"
                 and e.get("monotonic_ns", 0) < stamp]
        active = max(prior, key=lambda e: e["monotonic_ns"]).get("path") if prior else None
        bounded = [e for e in controller_events if e.get("monotonic_ns", 0) < end]
        result = recovery_metrics([e for e in progress if e["monotonic_ns"] < end], bounded, stamp, failed_path)
        inactive = active is not None and active != failed_path
        if inactive:
            result = recovery_metrics([], [], None, failed_path)
            result.update(failure_monotonic_ns=stamp, recovery_status="inactive_path")
        records.append(dict(active_path=active, failed_path=failed_path,
                            classification=("inactive_primary_flap" if failed_path == "upper" else "inactive_path_flap")
                            if inactive else "active_or_unknown", **result))
    return records


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
    trial_id = f"{scenario}-{mode}-{args.rto}-{args.sack}-{args.cc}-loss{args.loss}-fail{args.fail_after}-flap{args.flap_period}-{args.initial_path}-{args.failure_path}-{repeat:02d}"
    directory = args.output / trial_id
    directory.mkdir()
    controller_events = directory / "controller.jsonl"
    controller = None
    network = None
    handles, clients, servers, outputs, progress_files = [], [], [], [], []
    failure_ns = None
    interventions = []
    next_flap_ns = None
    flap_down = False
    failure_end_ns = None
    failed_path = args.initial_path
    soft_injected = False
    error = ""
    loss = args.loss if scenario in ("loss", "link-failure", "flap", "robust") else 0
    try:
        controller_log = (directory / "controller.log").open("w")
        handles.append(controller_log)
        env = os.environ.copy()
        env.update(RUDP_MODE=mode, RUDP_EVENT_LOG=str(controller_events), RUDP_INITIAL_PATH=args.initial_path)
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
        wait_until(lambda: any(e.get("event") == "route_ready" and e.get("path") == args.initial_path
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
        if scenario == "robust":
            impairments = load_module(ROOT / "mininet/link_impairment.py", "lab_impairment")
            impairments.set_host_reordering(network, args.reorder)
        save_network_state(network, directory, "initial")
        for flow in range(args.flows):
            output = directory / f"received-{flow}.bin"
            outputs.append(output)
            progress_files.append(directory / f"progress-{flow}.jsonl")
            server_log = (directory / f"server-{flow}.log").open("w")
            handles.append(server_log)
            server = h2.popen([str(ROOT / "src/server"), str(9000 + flow), str(output)],
                              env={**os.environ, "RUDP_PROGRESS_LOG": str(directory / f"receiver-{flow}.jsonl")},
                              stdout=server_log, stderr=subprocess.STDOUT)
            servers.append(server)
            wait_until(lambda f=flow: "Listening on UDP port" in
                       (directory / f"server-{f}.log").read_text(),
                       3, "UDP receiver", server)
        for flow in range(args.flows):
            client_log = (directory / f"client-{flow}.log").open("w")
            handles.append(client_log)
            client_env = os.environ.copy()
            client_env.update(RUDP_PROGRESS_LOG=str(progress_files[flow]),
                              RUDP_RTO=args.rto,
                              RUDP_SACK="1" if args.sack == "bitmap" else "0",
                              RUDP_CC="1" if args.cc == "on" else "0")
            clients.append(h1.popen([str(ROOT / "src/client"), h2.IP(), str(9000 + flow),
                                     str(source)], env=client_env,
                                    stdout=client_log, stderr=subprocess.STDOUT))
        deadline = time.monotonic() + args.timeout
        first_progress_ns = None
        displayed_generations = set()
        while any(client.poll() is None for client in clients):
            for event in read_events(controller_events):
                if event.get("event") == "route_ready" and event["generation"] not in displayed_generations:
                    displayed_generations.add(event["generation"])
                    print(f"ROUTE READY path={event['path']} cause={event['cause']} "
                          f"monotonic_ns={event['monotonic_ns']}", flush=True)
            if controller.poll() is not None:
                raise RuntimeError("Controller exited during transfer")
            if time.monotonic() > deadline:
                raise RuntimeError("Transfer deadline exceeded")
            if scenario in ("link-failure", "flap", "robust", "soft-degradation") and failure_ns is None and not soft_injected:
                events = [read_events(path) for path in progress_files]
                started = [[e for e in flow if e.get("event") == "ack_progress"
                            and e.get("base", 0) > 0] for flow in events]
                if all(started):
                    if first_progress_ns is None:
                        first_progress_ns = max(flow[0]["monotonic_ns"] for flow in started)
                    if monotonic_ns() - first_progress_ns >= args.fail_after * 1e9:
                        if any(client.poll() is not None for client in clients):
                            raise RuntimeError("Transfer ended before failure; increase --file-size")
                        current_routes = [e for e in read_events(controller_events) if e.get("event") == "route_ready"]
                        failed_path = (current_routes[-1]["path"] if current_routes else args.initial_path) if args.failure_path == "active" else args.failure_path
                        if failed_path not in ("upper", "lower"):
                            raise RuntimeError("No active route to fail")
                        branch = "s2" if failed_path == "upper" else "s3"
                        if scenario == "soft-degradation":
                            stamp = monotonic_ns()
                            impairments = load_module(ROOT / "mininet/link_impairment.py", "lab_impairment")
                            impairments.set_link_loss(network, "s1", branch, args.degrade_loss)
                            interventions.append(dict(event="degradation_injected", path=failed_path,
                                                      monotonic_ns=stamp, loss_percent=args.degrade_loss))
                            soft_injected = True
                            print(f"SOFT DEGRADATION {failed_path}: {args.degrade_loss}% link loss", flush=True)
                            continue
                        failure_ns = monotonic_ns()
                        network.configLinkStatus("s1", branch, "down")
                        print(f"LINK DOWN {failed_path}; transfer remains active", flush=True)
                        failure_end_ns = monotonic_ns()
                        flap_down = True
                        next_flap_ns = failure_end_ns + int(args.flap_period * 1e9 / 2)
                        interventions.append(dict(event="failure_injected", monotonic_ns=failure_ns,
                                                  command_end_ns=failure_end_ns, path=failed_path))
            if scenario in ("flap", "robust") and next_flap_ns is not None and monotonic_ns() >= next_flap_ns:
                stamp = monotonic_ns()
                flap_down = not flap_down
                network.configLinkStatus("s1", "s2" if failed_path == "upper" else "s3", "down" if flap_down else "up")
                interventions.append(dict(event="failure_injected" if flap_down else "link_restored",
                                          monotonic_ns=stamp, command_end_ns=monotonic_ns(), path=failed_path))
                next_flap_ns = monotonic_ns() + int(args.flap_period * 1e9 / 2)
            time.sleep(0.02)
        if scenario in ("link-failure", "flap", "robust", "soft-degradation") and failure_ns is None and not soft_injected:
            raise RuntimeError("No failure injected; increase --file-size or reduce --fail-after")
        if scenario == "soft-degradation" and not soft_injected:
            raise RuntimeError("No soft degradation injected; increase --file-size")
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
    (directory / "interventions.jsonl").write_text("".join(json.dumps(e) + "\n" for e in interventions))
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
        expected = not (scenario == "link-failure" and mode == "static" and failed_path == args.initial_path)
        progress = read_events(directory / f"progress-{flow}.jsonl")
        outages = outage_metrics(progress, events, interventions)
        recovery = ({k: v for k, v in outages[0].items() if k not in ("active_path", "failed_path", "classification")}
                    if outages else recovery_metrics(progress, events, failure_ns, failed_path))
        (directory / f"outages-{flow}.json").write_text(json.dumps(outages, indent=2) + "\n")
        intervention_ok = (scenario not in ("link-failure", "flap", "robust") or failure_ns is not None)
        if scenario == "link-failure" and mode == "failover":
            intervention_ok = intervention_ok and recovery["recovery_status"] == "recovered"
        if scenario in ("flap", "robust"):
            intervention_ok = intervention_ok and len(interventions) >= 3
            if mode == "failover":
                intervention_ok = intervention_ok and any(e.get("event") == "route_ready"
                    and e.get("path") != failed_path and e["monotonic_ns"] > failure_ns for e in events)
        if scenario == "soft-degradation":
            injection = next((e for e in interventions if e["event"] == "degradation_injected"), None)
            soft_route = next((e for e in events if injection and e.get("event") == "route_ready"
                               and e.get("cause") == "health_update" and e.get("path") != injection["path"]
                               and e["monotonic_ns"] > injection["monotonic_ns"]), None)
            intervention_ok = injection is not None and (mode == "static" or soft_route is not None)
            if soft_route:
                print(f"HEALTH ROUTE READY {soft_route['path']}", flush=True)
        if not expected:
            intervention_ok = (intervention_ok and client_exit not in (None, 0)
                               and server_exit not in (None, 0)
                               and "Retry limit reached for DATA" in client_text
                               and "transfer incomplete" in server_text
                               and not output.exists())
        # An infrastructure exception never counts as the expected static failure.
        expectation_met = not error and intervention_ok and success == expected
        row = dict(run_id=trial_id, scenario=scenario, mode=mode, repeat=repeat,
                   rto=args.rto, sack=args.sack, cc=args.cc, fail_after=args.fail_after,
                   initial_path=args.initial_path, failure_path=failed_path,
                   reorder_percent=args.reorder if scenario == "robust" else 0,
                   degrade_loss_percent=args.degrade_loss if scenario == "soft-degradation" else 0,
                   flap_period=args.flap_period, intervention_count=len(interventions),
                   retransmit_fraction=(sent.get("retransmits", 0) / sent["data_sends"] if sent.get("data_sends") else None),
                   flow_id=flow, flow_count=args.flows, file_bytes=args.file_size,
                   bandwidth_mbps=args.bandwidth, delay=args.delay, loss_percent=loss,
                   client_exit=client_exit, server_exit=server_exit,
                   sha256_match=output_hash == source_hash, success=success,
                   expected_success=expected, expectation_met=bool(expectation_met),
                   seconds=sent.get("seconds"), goodput_mbps=sent.get("goodput_mbps"),
                   data_packets=sent.get("packets", (args.file_size + 1023) // 1024),
                   data_sends=sent.get("data_sends", sum(e.get("event") in ("send", "retransmit") for e in progress)),
                   retransmits=sent.get("retransmits", sum(e.get("event") == "retransmit" for e in progress)),
                   control_retransmits=sent.get("control_retransmits"),
                   duplicates=received.get("duplicates"), out_of_order=received.get("out_of_order"),
                   failure_command_end_ns=failure_end_ns,
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
    parser.add_argument("--scenarios", nargs="+", choices=["normal", "loss", "link-failure", "flap", "robust", "soft-degradation"],
                        default=["normal", "loss", "link-failure"])
    parser.add_argument("--modes", nargs="+", choices=["static", "failover"], default=["static", "failover"])
    parser.add_argument("--initial-path", choices=["upper", "lower"], default="upper")
    parser.add_argument("--failure-path", choices=["upper", "lower", "active"], default="active")
    parser.add_argument("--reorder", type=float, default=20)
    parser.add_argument("--degrade-loss", type=float, default=35)
    parser.add_argument("--rtos", nargs="+", choices=["fixed", "adaptive"], default=["fixed", "adaptive"])
    parser.add_argument("--sacks", nargs="+", choices=["plain", "bitmap"], default=["plain", "bitmap"])
    parser.add_argument("--ccs", nargs="+", choices=["off", "on"], default=["off", "on"])
    parser.add_argument("--loss-rates", nargs="+", type=float)
    parser.add_argument("--failure-times", nargs="+", type=float)
    parser.add_argument("--flap-periods", nargs="+", type=float, default=[1, 4])
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
            or args.fail_after < 0 or args.timeout <= 0 or not 0 <= args.reorder <= 100
            or not 0 <= args.degrade_loss <= 100):
        parser.error("Invalid repeat/flow/file-size/bandwidth/loss/timing value")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:ms|us|s)", args.delay):
        parser.error("--delay must be a nonnegative duration such as 5ms")
    if any(not 0 <= value <= 100 for value in (args.loss_rates or [])) or any(
            value < 0 for value in (args.failure_times or [])) or any(value <= 0 for value in args.flap_periods):
        parser.error("Invalid matrix loss, failure time, or flap period")
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
        default_loss, default_failure = args.loss, args.fail_after
        for scenario in args.scenarios:
            losses = (args.loss_rates or [default_loss]) if scenario in ("loss", "link-failure", "flap", "robust") else [0]
            failures = (args.failure_times or [default_failure]) if scenario in ("link-failure", "flap", "robust", "soft-degradation") else [default_failure]
            periods = args.flap_periods if scenario in ("flap", "robust") else [args.flap_periods[0]]
            for mode, rto, sack, cc, loss, failure, period, repeat in itertools.product(
                    args.modes, args.rtos, args.sacks, args.ccs, losses, failures, periods,
                    range(1, args.repeats + 1)):
                args.rto, args.sack, args.cc = rto, sack, cc
                args.loss, args.fail_after, args.flap_period = loss, failure, period
                print(f"Running {scenario} {mode} {rto} {sack} cc={cc} repeat={repeat}", flush=True)
                trial = run_trial(args, topology, scenario, mode, repeat, source, source_hash)
                rows.extend(trial)
                write_metrics(args.output, rows)
                for row in trial:
                    print(f"  success={row['success']} sha256_match={row['sha256_match']} "
                          f"recovery={row['progress_recovery_seconds']}s goodput={row['goodput_mbps']} "
                          f"expected={row['expectation_met']} error={row['error']}", flush=True)
    finally:
        if source.exists() and not args.keep_files:
            source.unlink()
    print(f"Results: {args.output / 'metrics.csv'}")
    return 0 if rows and all(row["expectation_met"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
