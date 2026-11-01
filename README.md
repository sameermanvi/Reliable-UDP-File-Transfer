# Reliable UDP file transfer with SDN failover

Transfer a binary file over UDP while an SDN controller routes around a failed
or degraded network path. The C application repairs missing packets; the OS-Ken
controller restores reachability through a four-switch Mininet diamond.

**Verified:** 48 tests, 60/60 localhost transfers, and 180/180 Linux trial
expectations across three repeats: 132 hash-matched successes and 48 expected
static-routing failures. Linux measurements used **Ubuntu 22.04 Docker/userspace
OVS**, not the kernel datapath. [Results and limits](docs/KEY_RESULTS.md).

Build and test on macOS or Linux (C11 compiler, Make and Python 3):

```sh
make
make test
```

For a prepared Linux Docker host, demonstrate one transfer surviving link failure:

```sh
docker build -t rudp-lab .
docker run --rm --privileged -v "$PWD/results:/project/results" rudp-lab python scripts/demo.py --mode failover --output "results/demo-$(date +%Y%m%d-%H%M%S)"
```

Expect `LINK DOWN`, alternate `ROUTE READY`, then `success=True` and
`sha256_match=True`. [Demo setup, native Linux and static contrast](docs/DEMO.md).

## Application and controls

Start the client in a second terminal within ten seconds of the receiver:

```sh
./src/server 9000 received.bin
./src/client 127.0.0.1 9000 input.bin
cmp input.bin received.bin
```

Each receiver handles one upload. It verifies size and whole-file CRC before
atomically replacing the destination; failed transfers preserve existing output.
The experiment harness independently compares SHA-256 digests.

| Client switch | Values | Default |
| --- | --- | --- |
| `RUDP_RTO` | `fixed`, `adaptive` | `adaptive` |
| `RUDP_SACK` | `0` (individual ACK), `1` (bitmap) | `1` |
| `RUDP_CC` | `0` (fixed window), `1` (capped congestion window) | `1` |

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
docker run --rm --privileged -v "$PWD/results:/project/results" rudp-lab python scripts/evaluate.py --output "results/evaluation-$(date +%Y%m%d-%H%M%S)"
```

| Location | Purpose |
| --- | --- |
| `src/` | C sender, receiver, packet serialization and socket helpers |
| `controller/` | Path policy, bidirectional probes and OpenFlow handlers |
| `mininet/` | Diamond topology and netem impairments |
| `scripts/` | Setup, demo, evaluation, local benchmark and plots |
| `tests/` | Protocol, transport, controller and integration tests |
| `results/` | Final Linux/local evidence and labelled historical archive |
| `docs/` | [Architecture](docs/ARCHITECTURE.md), [code map](docs/CODE_MAP.md), [design decisions](docs/DESIGN_DECISIONS.md), [validation](docs/VALIDATION.md), [report](docs/REPORT.md), [viva](docs/VIVA.md), [rubric](docs/RUBRIC_MAPPING.md) |

This is a topology-specific lab implementation, not a production transport.
It provides no authentication, encryption, persistent resume or TCP fairness.
[MIT license](LICENSE).
