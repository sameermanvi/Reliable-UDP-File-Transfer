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
