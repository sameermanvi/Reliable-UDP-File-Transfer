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

## Real integration evidence retained, not relabeled

The 29 October Mininet archive contains real controller and application logs.
A selected trial was extracted without alteration and analyzed with current
path-independent recovery logic. It yields 0.196215 s from controller link_down
to useful ACK (0.199520 s from injection). See
[provenance](../results/rubric-integration-history/provenance.json),
[exact timestamps](../results/rubric-integration-history/recovery.json), and
[joined plot](../results/rubric-integration-history/timeline.svg).
This validates the historical integration only; its source fingerprint differs
from the new transport/probe implementation.

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

The separate [Ubuntu 22.04 preflight](../results/preflight-ubuntu22/metrics.csv)
passed 1/1 with matching SHA-256 and upper→lower recovery of 42.392 ms from
link_down (44.324 ms from injection). Its logs and timeline were inspected but
are excluded from final evaluation counts and the commit. The failed Python 3.14
preflight remains failed evidence and is not used to claim success.

Retained final evidence includes [runner 0](../results/rubric-final/runner-0.log),
[runner 1](../results/rubric-final/runner-1.log),
[runner 2](../results/rubric-final/runner-2.log), and each bundle's environment,
CSV/JSON metrics, summary plots, controller/progress/receiver events, endpoint
logs, network dumps, interventions, outages and per-trial joined timelines.

An earlier local test attempt used the wrong assertion that the global RTO must
reach 2 s while the base remained fixed. The corrected adversarial test checks
the per-slot backoff cap; global backoff is once per outstanding-window epoch.
Only rubric-final-native is the final passing local bundle.

The following records are historical and do not validate the new probe controller.

---

# Restoration validation — 30 October 2026

Restored the advanced implementation from `49f9ae6`, immediately before
simplification `19312e7`, using selective Git file restoration. The nested
repository was clean. Its original HEAD snapshot is saved in
`/tmp/rudp-before-restoration-19312e7.tar`; Git history was left unchanged.
Newer root build aliases, Compose support, launchers, demo runner, local tests,
and simplified-revision evidence were retained. Demo/test parsers were adapted
to the restored session-aware wire format and JSONL progress.

Executed on macOS:

- Clean native C11 build with `-Wall -Wextra -Wpedantic -Werror`: PASS.
- `python3 tests/test_protocol.py`: 7 tests PASS (38.667 seconds), including
  10 transfers through 1 MiB, SHA-256/CRC integrity, bidirectional packet faults,
  retransmission, session isolation, atomic output and bounded termination.
- `python3 tests/test_controller.py`: 10 tests PASS.
- `python3 tests/test_metrics.py`: 6 tests PASS.
- `python3 tests/test_local.py`: 5 tests PASS (26.431 seconds), including
  2 MiB binary transfers, selective retransmission and verified replacement.
- Metrics summary generation from restored historical CSV: PASS (`--no-plots`).
- `git diff --check` and launcher shell syntax checks: PASS.

Docker, Linux Mininet/OpenFlow integration and the retained Mininet demo have
not been executed in this restoration session. Docker remains optional; native
UDP execution is the primary workflow. No historical browser UI was found;
restored visualizations are the SVG evaluation plots and their generator.

The following sections are historical records, not newly executed checks.

---

# Core validation record

Validated locally on macOS on 25 October 2026. These are correctness checks,
not FTP throughput benchmarks or SDN recovery measurements.

## Normal build

```sh
make -C src
make -C src test
```

Result: all 6 test methods passed. The transfer method includes 10 independent
transfers: 0, 1, 1023, 1024, 1025, 32768, 32769 and 1048576 bytes without injected
faults, plus 32769 and 262267 bytes with deterministic faults. Every successful
transfer matched the original bytes, SHA-256 and advertised CRC-32.

Injected faults cover START, START_ACK, DATA, DATA ACK, FIN and FIN_ACK loss;
four successive FIN_ACKs are dropped. The proxy also corrupts a DATA payload,
duplicates DATA/ACKs and delays a DATA packet to cause reordering.

Other test methods verify invalid arguments, malformed/truncated/oversized
packets, bad packet CRCs, wrong peers and transfer IDs, wrong DATA lengths,
premature FIN, out-of-range sequences, whole-file CRC rejection, missing FIN,
and retry exhaustion against a bound but unresponsive UDP socket. Failure cases
check that existing output survives and temporary output is removed.

## Instrumented build

```sh
make -C src clean
make -C src \
  CFLAGS='-std=c11 -O1 -g -Wall -Wextra -Wpedantic -Werror -fsanitize=address,undefined -fno-omit-frame-pointer' \
  LDFLAGS='-fsanitize=address,undefined'
make -C src test
```

Result: all 6 test methods passed with the instrumented executables. The project
was then rebuilt with its normal compiler flags. Compiler warnings and
`git diff --check` were clean.

## Remaining validation

At the time of this historical record, Linux compilation, Mininet link impairments,
real SDN path changes, long-RTT networks, large files near the sequence limit,
cross-host interoperability and comparative throughput benchmarks had not been run.
See the later validation record below for subsequent Linux and Mininet work.

## Validation on 29 October 2026

The current protocol suite passed all 7 tests on macOS and in the Linux Docker
container. The controller routing suite passed all 10 tests on both platforms;
the metrics suite passed all 6 tests on macOS. These results supplement the
historical six-test record above; they do not replace it.

The completed three-repeat Mininet evaluation met all 18 expected outcomes:
15 successful transfers with matching SHA-256 and three expected static-route
failures after link interruption. Normal and loss scenarios completed in both
routing modes; all three failover transfers survived the link failure.
Observed progress recovery ranged from 0.1952 to 0.1995 seconds (mean 0.1972 s).
See [measured summary](../results/evaluation-2026-10-29/plots/summary.md).

On 30 October, a separate concurrent trial transferred two files during the
same link failure. Both completed with matching SHA-256 (4.540 Mb/s each).
The 10 routing tests and 6 metrics tests also passed in Linux Docker.
See [concurrent metrics](../results/concurrent-2026-10-29/metrics.csv).

Each result directory contains environment details, metrics and a raw-log
archive with endpoint, controller, progress, flow-table and queue evidence.
The evaluation used Docker's userspace OVS datapath. Mininet reported that
resource limits could not be raised; virtualization and resource scheduling
limit how far these timings generalize to native hardware.

An earlier preflight contained an invalid trial where random loss prevented
the initial connectivity check. The runner now enables loss after that check
and before transfer. The complete evaluation above was rerun with that fix;
earlier debug logs are retained locally and excluded from the reported sample.
