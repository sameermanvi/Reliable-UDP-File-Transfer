# Experimental results

## Merged multipath and adaptive probe implementation

The implementation merged in PR #15 passed 67 tests on Linux ARM64. Four targeted Mininet transfers with multipath enabled finished with matching SHA-256 hashes. Hard failure recovered in 15.301 ms from upper to lower and 42.178 ms from lower to upper, measured from link down to the first useful ACK after route readiness. Soft degradation switched paths. In the healthy trial the ingress switch counted 3,636 upper and 3,633 lower marked packets. These are single trials. The following repeated experiments measured the earlier controller.

## Measurement definitions

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

## Local transport measurements: measured on macOS, three repeats per configuration

**48 automated tests passed. All 60/60 final localhost transfers completed with
matching recorded input/output SHA-256.** Each transfer is 64 KiB; the proxy delays
DATA/ACK directions equally and uses deterministic faults, not a bottleneck queue.

| Controlled comparison (CC off) | Before retries | After retries | Result |
| --- | ---: | ---: | --- |
| 260 ms nominal RTT, no loss: fixed → adaptive RTO, plain ACK | 64 | 32 | 50% fewer unnecessary retries |
| 10 ms nominal RTT, DATA 10 and ACKs 5–7 initially lost: plain → bitmap, fixed RTO | 4 | 1 | 75% fewer retries |
| 260 ms nominal RTT, same faults: fixed/plain → adaptive/bitmap | 72 | 33 | 54.2% fewer retries |

These counts were identical across all three repeats in each listed cell.
Goodput changed little: the high-delay fault case was 0.7093 versus 0.7090 Mb/s.
The gain here is lower extra traffic, not a claimed speedup. Fast gap recovery is
held on in both ACK modes. The first window still pays for an initial RTO that is
too short. At 10 ms RTT without faults, enabling CWND reduced mean goodput from
15.144 to 6.752 Mb/s on this short uncontended transfer; no fairness benefit is
claimed from this dataset.

Evidence: [test log](../results/rubric-final-native/tests.log),
[execution manifest](../results/rubric-final-native/evaluation.json),
[raw measurements and hashes](../results/rubric-final-native/transport/metrics.csv),
[full cell summaries](../results/rubric-final-native/transport/plots/summary.md).

Plots: [retry counts](../results/rubric-final-native/transport/plots/retransmits.svg),
[retry fraction](../results/rubric-final-native/transport/plots/retransmit_fraction.svg),
[goodput](../results/rubric-final-native/transport/plots/goodput_mbps.svg),
[adaptive RTO/CWND trace](../results/rubric-final-native/transport/trace/timeline.svg).

## Repeated Linux evaluation

[Manifest](../results/rubric-final/evaluation.json) and
[test log](../results/rubric-final/tests.log): **48 tests passed; 180/180 trial
expectations met, 132 successful transfers with matching recorded input/output
SHA-256, 48 expected permanent-failure static-routing failures.**

- Matrix: 168 trials; 24 normal and 48 loss successes, 48 upper→lower failover
  successes, 48 expected static failures.
- Lower→upper: 3/3 successful; robustness: 6/6 under 2% loss, 20% reordering
  and 0.5/2 s flaps; soft degradation: 3/3 successful with probe health-driven
  upper→lower changes and no link-down event.
- Across 57 recovered trial rows, ordered link_down→route_ready→first contiguous
  ACK advancement is confirmed. Link-down→ACK: median **85.554 ms**, mean
  **116.743 ms**, range **12.276–401.377 ms**. Injection→ACK is distinct:
  median 88.493 ms, mean 119.945 ms, range 14.076–405.743 ms.
- Keep 48 censored static recovery rows and 75 not-applicable rows as null.
  Per-intervention records separately retain 58 recovered, 48 censored and
  218 inactive-path outages; these are not the trial-level latency sample.

Environment: Ubuntu 26.04.1 ARM64 VM host; Ubuntu 22.04 Docker image,
Python 3.10.12, OVS 2.17.12, **userspace datapath**. Kernel datapath validation
is not claimed. Payloads were deleted by the runner; SHA-256 equality is verified
from retained digest records and endpoint completion, not a fresh payload rehash.

[Matrix](../results/rubric-final/matrix/metrics.csv),
[lower recovery](../results/rubric-final/lower-recovery/metrics.csv),
[robustness](../results/rubric-final/robustness/metrics.csv).

## Presentation plots

The [labelled recovery timeline](../results/presentation/timeline.svg) is regenerated
from the retained lower-recovery trial's progress, controller and outage records.
The [goodput comparison](../results/presentation/goodput_mbps.svg) is regenerated
from matrix/metrics.csv. Rows identify the configurations being compared. Each dot marks a mean and each line spans the observed range. Shared settings appear above the plot. These are new renderings of
the recorded measurements.
