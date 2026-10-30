# UE25CS243A Reliable UDP File Transfer

A C / POSIX sockets file uploader with application-level reliability and an SDN
failure-recovery lab. Selective Repeat keeps up to 32 DATA packets in flight;
individual ACKs, CRC-32, timeouts and bounded retransmissions recover loss and
reordering. An OS-Ken controller routes the same transfer through alternate
paths in a Mininet diamond when a link fails.

This is a custom reliable UDP protocol. It does not interoperate with FTP, FTPS,
SFTP or TFTP.

## Build and transfer a file

The C application runs on Linux or macOS with a C11 compiler and Make. Python 3
is required for the test harness.

```sh
make
```

Start the receiver, then start the sender in a second terminal within 10 seconds:

```sh
./src/server 9000 /tmp/received.bin
./src/client 127.0.0.1 9000 /path/to/input.bin
cmp /path/to/input.bin /tmp/received.bin
```

The receiver handles one upload and exits after a 6.4-second final-ACK linger.
Start a fresh receiver for each transfer. Independent receiver processes on
different ports can run concurrent transfers; there is no shared multi-client
service. Both programs return zero on success and nonzero on failure.

The receiver writes a temporary file beside the output. It replaces the output
only after validating the declared size and whole-file CRC. **A successful
transfer replaces an existing output file.** Ordinary failures preserve it and
remove the temporary file; forced termination may leave a `.part.*` file. Keep
the input file unchanged during upload.

## Check the protocol

```sh
make test
```

The tests generate real binary data and cover empty files, chunk/window
boundaries, loss in both directions, corruption, duplication, reordering,
malformed messages, session isolation, missing FIN and retry exhaustion.
Independent SHA-256 comparisons verify successful outputs. These tests do not
need Mininet or privileged network configuration.

Client summaries include transfer time, payload goodput, original DATA packets,
total DATA sends and retransmissions. Receiver summaries include duplicates and
out-of-order arrivals. See [metric definitions](docs/ARCHITECTURE.md#measurements).

## Run the SDN lab

Mininet requires Linux network namespaces and Open vSwitch. Use a dedicated
Ubuntu Linux lab machine or VM with root access. macOS can run the C application
and unit tests, but cannot run Mininet directly.

From the repository root, install the lab dependencies and build the binaries:

```sh
sudo bash scripts/setup_env.sh
```

Run repeated normal, packet-loss and link-failure cases with static routing and
automatic failover:

```sh
sudo .venv/bin/python scripts/run_experiments.py \
  --scenarios normal loss link-failure \
  --modes static failover --repeats 3 --output results/latest
.venv/bin/python scripts/plot_metrics.py results/latest/metrics.csv \
  --output results/latest/plots
```

Each trial uses the C endpoints inside Mininet, checks file integrity and saves
the endpoint and controller logs. The static link-failure case is expected to
exhaust its retry budget; the failover case is expected to finish through the
alternate path. Expected behavior is not a substitute for the generated run
record. See the [validation record](docs/VALIDATION.md) for what has actually run.

The [demo guide](docs/DEMO.md) covers manual topology inspection, failure
injection, concurrent transfers, troubleshooting and the evidence to present.

Docker is optional; native execution above is the primary workflow.
For the SDN lab on macOS, a Linux VM or Docker Desktop supplies Linux. Build the image, then
run it with network namespace privileges and a results-only bind mount:

```sh
docker build -t rudp-sdn .
mkdir -p results/docker
docker run --rm --privileged \
  -v "$PWD/results/docker:/project/results/docker" rudp-sdn \
  python scripts/run_experiments.py --datapath user --repeats 3 \
  --output results/docker/evaluation
docker run --rm --entrypoint python \
  -v "$PWD/results/docker:/project/results/docker" rudp-sdn \
  scripts/plot_metrics.py results/docker/evaluation/metrics.csv \
  --output results/docker/evaluation/plots
```

The newer Compose shortcut is also retained:

```sh
docker compose run --build --rm demo
```

It uses `scripts/demo.py`, adapted for restored JSONL progress and statistics.
That runner and Docker/Mininet execution have not been revalidated in this
restoration session; the comprehensive runner above is the primary SDN workflow.

The image builds its own Linux binaries. The userspace switch datapath avoids
requiring the Docker VM to provide an Open vSwitch kernel module. Use a fresh
output directory for each run.

## Project documentation

- [Architecture, topology and packet layout](docs/ARCHITECTURE.md)
- [Demo and experiment guide](docs/DEMO.md)
- [Viva questions](docs/VIVA.md)
- [Report structure and interpretation](docs/REPORT.md)
- [Assignment checklist and rubric mapping](docs/RUBRIC_MAPPING.md)
- [Validation record](docs/VALIDATION.md)
- [Design decisions and references](docs/DESIGN_DECISIONS.md)

The earlier [stop-and-wait implementation](examples/stop_and_wait/README.md)
is preserved with its matching receiver. Its wire format is incompatible with
the current `src/client` and `src/server`; use each pair together. The SDN
comparison holds the current transfer protocol constant and changes only the
routing policy.

## Scope and limits

The protocol uses a fixed window and 200 ms retry interval, with at most 30
retries per packet. It does not implement adaptive congestion control, RTT
estimation, encryption, authentication or restart/resume. An outage longer than
the retry or receiver inactivity budget can fail the transfer. CRC-32 detects
accidental corruption; the independent SHA-256 check belongs to the test and
experiment harness, not the wire protocol.

The SDN controller is designed for the supplied diamond and detects link state
changes through OpenFlow port status events. It does not claim general topology
discovery or congestion-aware routing. Use controlled lab networks for these
experiments.

## License

[MIT](LICENSE).
