# Final rubric validation — 31 October 2026

## Executed final-source local checks

The one-command evaluation completed with status `passed`:

```sh
python3 scripts/evaluate.py --output results/rubric-final-native --local-only
```

- **48 tests passed**: 8 protocol, 5 adversarial transport, 4 probe tracking,
  3 recording-adapter OpenFlow, 12 routing, 11 metrics, 5 local integration tests.
- Coverage includes legacy/bitmap negotiation, unknown header versions, malformed
  and impossible SACKs, duplicate-ACK evidence, fixed/adaptive mode, Karn exclusion,
  50–2000 ms timer bounds, CWND cap, corruption, loss, reordering, atomic replacement,
  bounded failure, recovery on either branch, repeated failures and censored recovery.
- **60/60 three-repeat localhost benchmark transfers** succeeded with recorded
  matching input/output SHA-256. Raw traces and all configuration fields are saved.
- Warning-enabled C11 build, Python syntax checks and diff whitespace checks pass.

Artifacts: [manifest](../results/rubric-final-native/evaluation.json),
[complete test log](../results/rubric-final-native/tests.log),
[benchmark log](../results/rubric-final-native/benchmark.log),
[metrics/hashes](../results/rubric-final-native/transport/metrics.csv),
[environment/source fingerprint](../results/rubric-final-native/transport/environment.json),
[summary](../results/rubric-final-native/transport/plots/summary.md).
The native host is macOS. The OpenFlow adapter tests exercise the real controller
handlers against recorded messages; they are not a running OS-Ken switch test.

## Final Linux Docker validation — verified 31 October 2026

The retained [evaluation manifest](../results/rubric-final/evaluation.json) reports
`passed`, three repeats, starting at 13:28:20 UTC. All 60 configuration cells
contain repeats 1, 2 and 3. [Tests](../results/rubric-final/tests.log) passed
48 tests (8 protocol, 5 transport, 4 probes, 3 OpenFlow, 12 routing, 11 metrics,
5 local integration). Runner logs contain 168, 3 and 9 trials respectively,
all with `expected=True`, and no controller traceback.

| Bundle | Trials | Hash-matched successes | Expected static failures |
| --- | ---: | ---: | ---: |
| [Matrix](../results/rubric-final/matrix/metrics.csv) | 168 | 120 | 48 |
| [Lower recovery](../results/rubric-final/lower-recovery/metrics.csv) | 3 | 3 | 0 |
| [Robustness](../results/rubric-final/robustness/metrics.csv) | 9 | 9 | 0 |
| Total | 180 | 132 | 48 |

All 180 `expectation_met` fields are true. Aggregate JSON, CSV and per-trial
JSON agree. Every successful row has equal input/output SHA-256, successful
endpoint exit codes and endpoint completion logs with the expected byte count.
Payloads were not retained (`keep_files=false`); hash verification is the runner's
recorded input/output digest comparison, not a new rehash of deleted payloads.
The 8 MiB input hash is
`956de95f8fbf243127b4242052fd396ece0969f9fb79ab84dd2d08e2dac4fd8c`;
the 16 MiB robustness/soft-degradation input hash is
`211cba1b86522400507e498fde24d8c7879c07222ef4a5743bc44c958830050f`.

Permanent failure: static fails as expected in 48/48 cases; upper→lower failover
succeeds in 48/48, lower→upper in 3/3. Normal succeeds in 24/24; loss cases
(0% and 2% controls) in 48/48. Robustness succeeds in 6/6 with 2% loss,
20% reordering and 0.5/2 s flap periods; retained intervention counts are
117, 117, 118 and 32, 31, 31. Soft degradation succeeds in 3/3: injecting
35% upper-branch loss produces upper→lower `health_update` decisions and
barrier-confirmed `route_ready`, without any `link_down` event. Controller
logs retain bidirectional probe samples and health scores.

### Recovery measurements

Every recovered trial was cross-checked against controller JSONL, progress JSONL,
endpoint logs and its joined `plots/timeline.svg`. The useful ACK is the first
`ack_progress` after `route_ready` whose contiguous base exceeds every base at or
before readiness. All 57 recovered trial rows have ordered injection ≤ link_down
≤ route_ready < useful ACK timestamps; all reported differences match the events.

| Trial-level measurement (57 recovered rows) | Minimum | Median | Mean | Maximum |
| --- | ---: | ---: | ---: | ---: |
| link_down → useful ACK (ms) | 12.276 | 85.554 | 116.743 | 401.377 |
| route_ready → useful ACK (ms) | 10.695 | 83.919 | 114.834 | 399.202 |
| Injection request → useful ACK (ms) | 14.076 | 88.493 | 119.945 | 405.743 |

Upper permanent-failure recovery (48 rows): link_down→ACK mean 132.651 ms,
median 147.342 ms, range 38.384–401.377 ms. Lower recovery (3 rows): mean
42.846 ms, median 42.968 ms, range 42.265–43.304 ms. Robust trials (6 rows):
mean 26.422 ms, median 17.061 ms, range 12.276–76.378 ms.
These are trial-level samples, not a pooled count of every flap.
Per-intervention `outages-0.json` records retain 58 recovered outages, 48
`censored_no_route` and 218 inactive-path flaps. The recovered outage timestamps
were also checked against the traces. Trial recovery status totals are 57
`recovered`, 48 `censored_no_route`, 75 `not_applicable` (including soft degradation).
Missing and censored values remain null; they are not zero or included in latency
statistics. Overall successful-transfer goodput ranges 2.999–9.313 Mb/s
(mean 7.385, median 9.060); configurations differ, so this is descriptive only.

### Environment and evidence boundaries

VM host: Ubuntu 26.04.1 LTS, ARM64/aarch64, kernel 7.0.0-42-generic.
The successful run used the project's Ubuntu 22.04 Docker image (see
[Dockerfile](../Dockerfile)); retained environment manifests record Python 3.10.12,
glibc 2.35, aarch64 and OVS 2.17.12. All three command manifests explicitly use
`--datapath user`: this validates userspace OVS, not the kernel datapath.
The container shares the VM kernel; it is not a native Ubuntu 22.04 host run.
Live Docker metadata inspection required terminal sudo authentication and was
unavailable during this audit; container release provenance is the Dockerfile,
user-reported Docker execution and the recorded runtime versions.

The separate Ubuntu 22.04 preflight (not included in this checkout)
passed 1/1 with matching SHA-256 and upper→lower recovery of 42.392 ms from
link_down (44.324 ms from injection). Its logs and timeline were inspected but
are excluded from final evaluation counts and the commit. The failed Python 3.14
preflight remains failed evidence and is not used to claim success.

Retained final evidence includes [runner 0](../results/rubric-final/runner-0.log),
[runner 1](../results/rubric-final/runner-1.log),
[runner 2](../results/rubric-final/runner-2.log), and each bundle's environment,
CSV/JSON metrics, summary plots, controller/progress/receiver events, endpoint
logs, network dumps, interventions, outages and per-trial joined timelines.


Historical material is preserved in [the archive](../results/archive/README.md).

## Source identity after repository cleanup

These measurements are retained from commit
`79f097dea2ae8f61e70dd4558816531dfbbb97a5`. This newer client/codec interface has separate localhost checks. The recorded Linux
measurements describe the earlier commit and its original source fingerprints.
