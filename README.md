# Reliable UDP file transfer with SDN failover

## One-command assessment menu

Run from the repository root.

```sh
make demo
```

Press **1–8** to select a stage, **a** to run stages 1–6, or **q** to quit.
The menu starts both C endpoints, waits for receiver readiness, streams their
output and verifies CRC32 and SHA-256. Stage 3 uses ports 9000 and 9001.
Stage 2 runs two independent 10% loss executions on the same 1 MiB payload.
Its A/B numbers describe those executions and can vary between runs.

SDN stages detect native Mininet/OVS or a running Docker engine. The Docker image
is rebuilt using cached layers to match this checkout. Network trials use fresh results directories and open the
generated timeline when a desktop viewer is available. Stage 5 always runs its
tests and reports when live SDN is unavailable. Stage 6 reads the retained
180-outcome evaluation, clearly labelled with its earlier measurement scope.
Stage 7 runs the complete current test suite. Stage 8 runs the browser console
until Ctrl-C returns to the menu.

For a single non-interactive stage use
`python3 scripts/run.py interactive --step 1`.
The alias `python3 scripts/run.py menu` opens the same menu. Some network tests
and static failures take longer than a ten-minute presentation, so rehearse and
select the stages needed for the assessment.


## Live telemetry console

Run the console from the repository root. It builds the C binaries and opens the browser.

```sh
python3 scripts/run.py viz
```

Choose one of the five numbered scenarios. The default 32-packet guided playback supports play, pause and single-event stepping. Advanced manual controls and raw logs are collapsed below the three main panels. The console captures actual
24-byte headers through a UDP relay, streams sender/receiver JSONL records, shows
the sender ring snapshots, and reports independent SHA-256 verification. The relay
adds 15 ms in each direction to make the transitions visible. **Drop next DATA**
discards one observed DATA datagram.

Load a trial from the selector or enter a directory under results/ and select
**Tail active trial** for a running Mininet experiment. Replay preserves recorded
monotonic timing with play, pause, single-step and speed controls. Older recordings
supply only the fields they retained. The localhost run supplies transport data,
while Mininet recordings supply controller events.


Transfer a binary file over UDP while an SDN controller routes around a failed
or degraded network path. The C11 transport implements Selective Repeat, SACK, adaptive RTO and congestion control. The Python OpenFlow 1.3 controller schedules adaptive probes, reroutes around failures and supports weighted multipath DATA.

## Try a file transfer on localhost

Use a C compiler and Make. Open two terminals in the repository:

1. Build: `make`
2. In terminal A: `./server 9000 received.bin`
3. Within ten seconds, in terminal B: `./client --host 127.0.0.1 --port 9000 --file README.md && cmp README.md received.bin`

A successful comparison prints nothing. Start a new receiver for each transfer.
For a visible retransmission demo, send a larger file and add `--drop-rate 0.05`
to the client command. Each outgoing DATA attempt has a 5% chance of simulated
loss. See `./client --help`. Run `make test` for automated checks (requires Python 3).

## Demonstrate SDN recovery

For a prepared Linux Docker host, demonstrate one transfer surviving link failure:

```sh
docker build -t rudp-lab .
docker run --rm --privileged -v "$PWD/results:/project/results" rudp-lab python scripts/run.py demo --mode failover --output "results/demo-$(date +%Y%m%d-%H%M%S)"
```

Expect `LINK DOWN`, alternate `ROUTE READY`, then `success=True` and
`sha256_match=True`. [Demo setup, native Linux and static contrast](docs/DEMO.md).

## Application and controls

Each receiver handles one upload. It verifies size and whole-file CRC before
atomically replacing the destination; failed transfers preserve existing output.
The experiment harness independently compares SHA-256 digests.

| Client switch | Values | Default |
| --- | --- | --- |
| `RUDP_RTO` | `fixed`, `adaptive` | `adaptive` |
| `RUDP_SACK` | `0` (individual ACK), `1` (bitmap) | `1` |
| `RUDP_CC` | `0` (fixed window), `1` (capped congestion window) | `1` |

Run `python3 scripts/run.py --help` for all lab commands, or
`python3 scripts/run.py benchmark --help` for localhost benchmark options.

The named client options override environment defaults. Use `--fixed-rto`,
`--no-sack` or `--no-cc` to select baselines. The codec explicitly serializes
fixed-width fields in network byte order and computes the CRC over wire bytes.
The 24-byte header never depends on native C structure padding.

Selective Repeat uses 32 slots; SACK, Karn-safe adaptive timers, bounded backoff,
fast gap retransmission and congestion control remain independently reproducible.
For example: `RUDP_RTO=fixed RUDP_SACK=0 RUDP_CC=0 ./src/client 127.0.0.1 9000 input.bin`.
Use a new receiver for each transfer. Old servers require `RUDP_SACK=0`.

## Evaluation and repository map

The full evaluation runs tests, a three-repeat routing/RTO/ACK matrix, reverse
recovery, soft degradation and loss/reordering/flaps. CC is off in that Linux
matrix; the separate local benchmark includes CC comparisons. It can take over
an hour. Use a fresh output directory; do not overwrite retained evidence.

```sh
docker run --rm --privileged -v "$PWD/results:/project/results" rudp-lab python scripts/run.py evaluate --output "results/evaluation-$(date +%Y%m%d-%H%M%S)"
```

| Location | Purpose |
| --- | --- |
| `src/` | C sender, receiver, packet serialization and socket helpers |
| `controller/` | Path policy, bidirectional probes and OpenFlow handlers |
| `mininet/` | Diamond topology and netem impairments |
| `scripts/` | Setup, demo, evaluation, local benchmark and plots |
| `tests/` | Protocol, transport, controller and integration tests |
| `results/` | Final Linux/local evidence |
| `docs/` | [Architecture](docs/ARCHITECTURE.md), [Report](docs/REPORT.md), [Demo](docs/DEMO.md), [Viva](docs/VIVA.md) |

This is a topology-specific lab implementation, not a production transport.
It provides no authentication, encryption, persistent resume or TCP fairness.
[MIT license](LICENSE).

## Measured failover

![Lower-branch failure and application recovery](results/presentation/timeline.svg)

The retained Linux trial shows the sequence of controller and application events.
Across the measured evaluation, 132 transfers matched their hashes and 48 static
failures were expected. [Measurements and scope](docs/REPORT.md).
