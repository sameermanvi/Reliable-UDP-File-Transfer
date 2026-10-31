# Key Results — 60-second assessment view

## Final transport: measured on macOS, three repeats per configuration

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

## Socket–SDN integration: real historical trace, separately labeled

A retained 29 October failover trial records:

| Observed sequence | Monotonic time / interval |
| --- | ---: |
| Controller link_down | 596653470563 ns |
| Alternate route_ready | 596655523230 ns |
| First new useful post-route ACK prefix | 596849685230 ns |
| link_down → useful ACK | 0.196215 s |
| Injection request → useful ACK | 0.199520 s |

Open the [joined timeline](../results/rubric-integration-history/timeline.svg),
[computed recovery](../results/rubric-integration-history/recovery.json) and
[provenance/original hash record](../results/rubric-integration-history/provenance.json).
This is evidence for the earlier integrated implementation, not new probe runtime
validation. Across the historical three-repeat network evaluation, static failed
all three permanent-link cases and failover completed all three; see the original
[summary](../results/evaluation-2026-10-29/plots/summary.md).

## Remaining assessed work on Linux

Run `sudo .venv/bin/python scripts/evaluate.py --output results/rubric-final`.
This generates the final routing/RTO/ACK/loss/failure-time matrix and validates
probe-driven soft rerouting, lower→upper recovery and loss/reordering/short flaps.
**No final-system Linux recovery number is claimed until that command passes.**
The current Docker daemon is unavailable; the [environment check](../results/rubric-linux-plan/environment-check.txt)
and [pending execution plan](../results/rubric-linux-plan/README.md) record that gap.
