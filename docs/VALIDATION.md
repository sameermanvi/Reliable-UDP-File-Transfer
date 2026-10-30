# Validation — 30 October 2026

This record applies to the simplified 16-packet Selective Repeat implementation
with a fixed 250 ms timeout. Older implementation results are not reused.

## Executed checks

- `make test`: all five test methods passed on macOS and Ubuntu 22.04 Docker.
- Eight byte-for-byte transfer cases: 0, 1, 1023, 1024, 1025, 16384, 16385 and
  2097152 bytes; four run concurrently on independent ports.
- Scripted peers check missing ACKs trigger only selective retries, repeated
  FINs receive ACKs, reordered/duplicate DATA is written once, corrupt/truncated
  datagrams are ignored, file CRC mismatches fail, and existing output survives.
- `docker compose build`: clean Linux compilation succeeded.
- `docker compose run --rm demo python scripts/demo.py --output results/validation`:
  all eight Mininet trials completed and every output matched source SHA-256.
- Python compilation, documentation links and Git whitespace checks passed.

## Measured comparison

Each file is 2 MiB. Both paths have 10 Mb/s inter-switch links and 5 ms egress
delay. Static and dynamic trials receive the same one-second s1–s2 outage after
20% of the input is acknowledged. Dynamic trials must install the lower path
and resume ACK progress before that second ends. Static waits for restoration.

| Scenario | Runs | Mean time (s) | Mean retransmissions | Mean recovery (s) |
| --- | ---: | ---: | ---: | ---: |
| Normal | 1 | 2.879 | 0 | N/A |
| Loss, duplication and reordering | 1 | 19.375 | 92 | N/A |
| Failure, static route | 3 | 4.123 | 80 | 1.261 |
| Failure, dynamic route | 3 | 3.098 | 16 | 0.259 |

The netem case applies 2% loss, 1% duplication, and 20% reordering with 50%
correlation, on top of 8 ms delay with 2 ms jitter at each host egress.
Dynamic route installation averaged 0.0088 seconds.
Recovery includes controller reaction and the sender's retry timer. These are
small lab samples, not statistical claims for other networks.

[CSV measurements](../results/validation/metrics.csv),
[environment and source fingerprint](../results/validation/environment.json), and
[raw logs](../results/validation/raw-logs.tar.gz) are included. Extract the archive
with `tar -xzf raw-logs.tar.gz` to inspect events, ACK progress and before/after
flow tables. The local source fingerprint matches the measured container.

## Limits

The live network used Docker Desktop's Linux aarch64 VM and userspace OVS.
Mininet warned that resource limits could not be raised; OS-Ken emitted an
Eventlet RLock warning. The controller nevertheless installed flows and passed
all link-change trials. Native Linux kernel-datapath commands are provided but
were not rerun for this rewrite. CI adds sanitizer checks; those are not claimed
as locally executed here. Direct output cleanup cannot remove partial files if
a process is forcibly killed. One server handles one transfer; concurrency uses
separate processes and ports. The original guide remains unchanged; the source
and this README define the simplified implementation.
