# Reliable UDP transfer with SDN recovery — final report

## Objective and assessed behavior

Transfer binary files correctly through loss, corruption, duplication and
reordering, while SDN restores a broken path during the same upload. The C
application provides Selective Repeat reliability; OS-Ken controls the Mininet
diamond. Correctness requires explicit completion, size/CRC agreement and final
independent SHA-256 equality. Silence is failure, never successful completion.

## Implementation

The final system has a version-1 24-byte header and an explicitly negotiated
bitmap ACK extension. Adaptive DATA RTO uses SRTT, variation, Karn sampling and
bounded backoff; distinct later ACK coverage supports fast retransmit. A capped
congestion window is independent of the 32-slot receiver window. Legacy ACK and
fixed-RTO modes remain selectable. Wire validation precedes state mutation.

Static routing keeps the initial branch. Failover routing immediately excludes
hard failures. Bidirectional Ethernet probes independently exercise both live
branches, including an idle backup. Fresh EWMA loss/elapsed-latency scores,
hysteresis and a route hold-down govern soft moves; hard failure bypasses the
hold-down. Barrier-confirmed route_ready and continued ACK progress remain
separate observations. Details and limits are in ARCHITECTURE.md.

## Method and metrics

The final Linux evaluation command is:

```sh
sudo .venv/bin/python scripts/evaluate.py --output results/rubric-final
```

It runs tests first, then at least three independent repetitions of routing ×
RTO × ACK format with 0/2% configured per-egress loss and failure times 0.5/1.5 s
after observed ACK progress. It additionally tests lower→upper recovery,
loss/reordering/short primary flaps and soft loss without link-down. CC is held off
in the main comparison to avoid confounding those axes. Source fingerprints,
environment, raw events, flow/queue dumps, all trial outcomes and hashes are saved.
Linux netem random draws and virtualization scheduling vary; the input generator
is seeded, which does not make the network stochastic process deterministic.

| Metric | Exact definition |
| --- | --- |
| Success | Both endpoint exits are zero; output size and independent SHA-256 match input |
| Goodput | File payload bits / client START-to-FIN_ACK interval, excluding metadata scan and receiver linger |
| Retransmissions | Extra DATA sends; includes retries caused by lost ACKs, not a loss-rate estimate |
| Completion rate | Successful flows / all observed flows, including expected static failures |
| Primary recovery latency | Matching controller link_down → first strictly later new contiguous ACK prefix after alternate route_ready |
| Injection recovery | Failure-command start → that same useful prefix advancement |
| Route installation | Failure-command start → barrier-confirmed alternate route_ready |
| Censored recovery | No qualifying route or later useful progress before observation ends/next intervention; reported N/A |

Reports retain failed rows and distinguish expected static failure from successful
transfer. Means/min–max use successful flows; numeric sample counts are explicit.
Multiple concurrent flows share one network trial and are not independent repeats.
Barrier completion is not globally atomic switching or proof of an ACK's physical
route. The final hash is independent evidence of application delivery.

## Executed findings and evidence

The final local evaluation passed 48 automated tests and 60/60 independently
hash-verified transfers. Adaptive RTO halved retries (64→32) at 260 ms nominal RTT
without loss. Bitmap feedback reduced retries 4→1 in the low-delay DATA/ACK-loss
case. Together they reduced high-delay fault retries 72→33. These are three-repeat
64 KiB localhost proxy comparisons, not Mininet throughput benchmarks. Goodput in
the high-delay fault case changed little (0.7093→0.7090 Mb/s). Capped slow start
lowered short uncontended-flow goodput; a fairness/queueing benefit was not tested.

Artifacts: [test log](../results/rubric-final-native/tests.log),
[hash-bearing metrics](../results/rubric-final-native/transport/metrics.csv),
[environment](../results/rubric-final-native/transport/environment.json),
[summaries/plots](../results/rubric-final-native/transport/plots/summary.md).
See KEY_RESULTS.md for the short table and direct plot links.

## Final Linux findings

The Ubuntu 22.04 container on the Ubuntu 26.04 ARM64 VM completed 180/180
trial expectations across three repeats: 132 hash-matched successes and 48
expected static failures. Upper→lower failover passed 48/48, lower→upper 3/3,
robustness 6/6 and probe soft degradation 3/3. The 57 recovered trial rows have
median link-down→useful-ACK latency 85.554 ms, mean 116.743 ms, and range
12.276–401.377 ms. Censored outcomes remain null and are excluded from latency
statistics. These are userspace OVS measurements, not physical-switch or kernel
OVS results. [Validation](VALIDATION.md) defines the samples and evidence limits;
[metrics](../results/rubric-final/matrix/metrics.csv) retain individual outcomes.

## Deliberate limits

This is a topology-specific lab uploader, not TCP or an FTP-compatible service.
It omits authentication, encryption, persistent resume, arbitrary topology
discovery, mature fairness/pacing and crash durability. Probes include control
channel delay and sample loss noisily. Window 32 caps memory and throughput.
Long outages exceed inactivity/retry budgets. Virtualized userspace OVS timings
must not be generalized to physical switches without measurement. No frontend
or unrelated portfolio work was needed for the rubric.
