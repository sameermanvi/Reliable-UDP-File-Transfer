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

Historical integration evidence is kept separate. A 29 October real Mininet
trial shows link_down → route_ready → useful ACK in 0.196215 s from observed
link-down (0.199520 s from injection). Its exact timestamps, original output hash
record and archive identity are retained in
[historical provenance](../results/rubric-integration-history/provenance.json) and
[recovery analysis](../results/rubric-integration-history/recovery.json).
The original [three-repeat evaluation](../results/evaluation-2026-10-29/plots/summary.md)
has 3/3 failover successes versus 0/3 expected static successes under permanent
failure. Those results describe that historical source revision only.

## Validation still required before submission

Final adaptive-transport + probe-controller Mininet execution is **pending**.
The native environment is macOS and the Docker daemon is unavailable; see the
[pending plan](../results/rubric-linux-plan/README.md) and
[environment evidence](../results/rubric-linux-plan/environment-check.txt).
Do not claim final Linux hard-failure recovery, probe-driven soft recovery or
combined netem/flap robustness until the final evaluation produces successful
hash-verified artifacts. Policy/probe tests and recording-adapter OpenFlow tests
check logic and messages; they do not substitute for real switches.

## Deliberate limits

This is a topology-specific lab uploader, not TCP or an FTP-compatible service.
It omits authentication, encryption, persistent resume, arbitrary topology
discovery, mature fairness/pacing and crash durability. Probes include control
channel delay and sample loss noisily. Window 32 caps memory and throughput.
Long outages exceed inactivity/retry budgets. Virtualized userspace OVS timings
must not be generalized to physical switches without measurement. No frontend
or unrelated portfolio work was needed for the rubric.
