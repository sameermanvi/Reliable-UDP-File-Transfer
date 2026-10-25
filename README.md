# UE25CS243A Reliable UDP File Transfer

A pure C / POSIX sockets implementation of reliable, binary file upload over UDP.
The client sends a file; the server writes it to a locally chosen output path.
Reliability uses Selective Repeat with a 32-packet window, individual ACKs,
CRC-32 checksums, timeouts, and bounded retransmissions.

## Build and run

Requires a C11 compiler and Make on Linux or macOS. Python 3 is needed only for tests.

```sh
make -C src
```

Start the receiver, then run the sender in another terminal:

```sh
./src/server 9000 /tmp/received.bin
./src/client 127.0.0.1 9000 /path/to/input.bin
cmp /path/to/input.bin /tmp/received.bin
```

Both programs return zero on success and nonzero on failure. The server handles
one upload and exits after a 6.4-second final-ACK linger. Start a fresh server for
each transfer. It waits up to 10 seconds for START or valid in-window DATA.
The client retries an unacknowledged packet every 200 ms, up to 30 retries.
Start the client within 10 seconds of the server.

The receiver writes a unique temporary file beside the requested output. Only a
complete transfer with the advertised size and whole-file CRC replaces the output
path. **Successful transfers replace an existing output file.** Ordinary failures
remove the temporary file and preserve any previous output. Forced termination
may leave a `.part.*` file. Keep the input file unchanged during upload.

## Verify reliability

```sh
sh scripts/test_transfer.sh
# Equivalent: make -C src test
make -C src clean
```

Tests generate real binary contents in temporary directories; the original empty
sample files are not used as evidence of successful binary transfer. They check
empty files, chunk/window boundaries, a 1 MiB file, bidirectional packet/ACK loss,
corruption, duplication, reordering, malformed packets, session isolation,
whole-file CRC rejection, missing FIN, and retry exhaustion. SHA-256 is checked
independently by the tests. No privileged network configuration is required.

Client summaries report file bytes, CRC-32, original DATA packet count, total DATA
sends, DATA/control retransmissions, elapsed seconds, and payload goodput in Mb/s.
Server summaries report duplicates and out-of-order arrivals.

## Design and project scope

- [Architecture and packet layout](docs/ARCHITECTURE.md)
- [Design choices, references, and honest comparisons](docs/DESIGN_DECISIONS.md)
- [Checklist and rubric mapping](docs/RUBRIC_MAPPING.md)
- [Validation record](docs/VALIDATION.md)

The protocol is designed for controlled lab experiments. A fixed window and retry
interval keep the implementation easy to trace; adaptive congestion control,
RTT estimation, encryption, authentication, multi-client service, restart/resume,
and SDN/Mininet path switching are not implemented. CRC detects accidental
corruption and is not a cryptographic integrity check. This protocol does not
interoperate with FTP, FTPS, SFTP, or TFTP.

## License

This project is licensed under the [MIT License](LICENSE).
