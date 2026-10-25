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

Linux compilation, Mininet link impairments, real SDN path changes, long-RTT
networks, large files near the sequence limit, cross-host interoperability and
comparative throughput benchmarks have not been run in this phase.
