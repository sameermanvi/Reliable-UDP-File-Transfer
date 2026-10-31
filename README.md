# Reliable UDP transfer with dynamic SDN recovery

A C/POSIX Selective Repeat uploader and OS-Ken controller on a Mininet diamond.
The application recovers missing datagrams while the controller restores network
reachability. The live demo keeps one upload running across a path failure and
verifies the completed file with SHA-256.

## Features and validation

- Selective Repeat with a 32-packet receive window, negotiated SACK bitmap,
  adaptive RTO with Karn sampling, and fast gap retransmission.
- Capped congestion control, with independent switches for controlled comparisons.
- Static/failover routing and bidirectional health probes with hysteresis.
- Monotonic JSONL events, joined recovery timelines, and repeatable experiments.

**Verified locally:** 48 automated tests and 60/60 hash-verified transfers.
**Validated:** Linux Docker/userspace OVS, three repeats: 180/180 expectations met, 132 hash-matched transfers and 48 expected static failures ([evidence](results/rubric-final/evaluation.json)).
See [Key Results](docs/KEY_RESULTS.md) for measurements and their limits.

## Build and test

Linux or macOS: C11 compiler, Make, Python 3 (no Python packages for local tests).

```sh
git clone https://github.com/sameermanvi/Reliable-UDP-File-Transfer.git
cd Reliable-UDP-File-Transfer
make
make test
```

In separate terminals, start the client within 10 seconds of the receiver:

```sh
./src/server 9000 /tmp/received.bin
./src/client 127.0.0.1 9000 /path/to/input.bin
cmp /path/to/input.bin /tmp/received.bin
```

Each receiver accepts one upload and exits after a 6.4 s FIN linger. Successful
verification atomically replaces its destination; ordinary failed transfers
preserve it. Keep the input unchanged. The protocol has packet CRC, transfer ID,
size and whole-file CRC, bounded retries and explicit FIN. It is not FTP or TCP.

## Reproducible transport switches

```sh
RUDP_RTO=fixed RUDP_SACK=0 RUDP_CC=0 ./src/client 127.0.0.1 9000 input.bin
RUDP_RTO=adaptive RUDP_SACK=1 RUDP_CC=0 ./src/client 127.0.0.1 9000 input.bin
```

Defaults: adaptive RTO, negotiated bitmap ACKs, capped congestion control on.
Start a new receiver for each command. `RUDP_RTO` accepts exactly fixed/adaptive;
`RUDP_SACK=0` selects the original wire exchange for old endpoints. An old server
cannot negotiate the default bitmap extension. The fixed 24-byte v1 header and
all packet types are documented in [ARCHITECTURE.md](docs/ARCHITECTURE.md).

Set `RUDP_PROGRESS_LOG` to a fresh path on each endpoint for flushed JSONL events.
Use different sender/receiver paths. Both files and controller logs use monotonic
nanoseconds; never compare clocks from different physical machines.

## Live failover demo on Linux

Ubuntu 22.04 is the supplied setup target. Setup needs network package access:

```sh
sudo sh scripts/setup_env.sh
sudo .venv/bin/python scripts/demo.py --mode failover --output results/live-failover
sudo .venv/bin/python scripts/demo.py --mode static --output results/live-static
```

The failover run starts controller/topology, starts an 8 MiB transfer, kills the
active branch after 0.5 s of real ACK progress, shows alternate route readiness,
and checks endpoint exits, output size and SHA-256. The static run must fail
without installing a finalized output. Each saves a joined timeline and logs.
See the one-page [live demo](docs/DEMO.md) for lower→upper recovery, soft degradation,
loss/reordering/flaps, expected console output and Docker commands.

## One command for the final evaluation

```sh
sudo .venv/bin/python scripts/evaluate.py --output results/rubric-final
```

This runs the full suite, then a three-repeat static/failover × fixed/adaptive ×
plain/bitmap comparison with loss rates 0/2% and fault times 0.5/1.5 s. It also runs
lower→upper recovery, loss/reordering/short flaps and probe-driven soft degradation.
CC stays off in the main matrix to isolate those effects; local evaluation tests
and separately ablates CC. Permanent static failures take up to about a minute;
the full factorial evaluation can take well over an hour. Use `demo.py` first to
verify infrastructure. Use `--repeats 5` for five repeats; fresh output is required.

Expected output:

```text
results/rubric-final/
  evaluation.json, tests.log, runner-*.log, README.md
  matrix/                 # comparison matrix
  lower-recovery/         # reverse branch recovery
  robustness/             # probes, loss, reordering and flaps
    environment.json, metrics.csv, metrics.json, plots/
    TRIAL/controller.jsonl, progress-0.jsonl, receiver-0.jsonl
    TRIAL/client-0.log, server-0.log, interventions.jsonl, outages-0.json
    TRIAL/network-initial.txt, network-final.txt, plots/timeline.svg
```

Every successful row requires independent hash equality. All failed rows remain.
Plots cover goodput, retries, retry fraction, completion and recovery. Recovery
without a qualifying observation is N/A/censored, never zero.

Without Linux, produce a plan or run the transport evidence only:

```sh
python3 scripts/evaluate.py --output results/linux-plan --plan-only
python3 scripts/evaluate.py --output results/local-check --local-only
```

## Evidence and documentation

The final local bundle has **48 passing tests and 60/60 hash-verified transfers**:
[validation](docs/VALIDATION.md), [Key Results](docs/KEY_RESULTS.md),
[raw local metrics](results/rubric-final-native/transport/metrics.csv).
Final probe-controller/Mininet validation **passed in Ubuntu 22.04 Docker with userspace OVS**: [180-trial evidence](results/rubric-final/evaluation.json).
The retained [historical joined timeline](results/rubric-integration-history/timeline.svg)
demonstrates the earlier controller's real socket–SDN integration; it does not
validate the new probe controller. Do not mix historical and current source runs.

Assessment checklist: [rubric mapping](docs/RUBRIC_MAPPING.md).
Prioritized file changes: [completion plan](docs/RUBRIC_FINISH.md).
Technical defense: [viva](docs/VIVA.md). Findings and limits: [report](docs/REPORT.md).

## License

[MIT](LICENSE).
