# Live demonstration

## One-command assessment menu

Run from the repository root.

```sh
make demo
```

Press **1–8** to select a stage, **a** to run stages 1–6, or **q** to quit.
The menu starts both C endpoints, waits for receiver readiness, streams their
output and verifies CRC32 and SHA-256. Stage 3 uses ports 9000 and 9001.
Stage 2 runs two independent 10% loss executions on the same 1 MiB payload.
Its A/B numbers describe those executions and can vary between runs.

SDN stages detect native Mininet/OVS or a running Docker engine. The Docker image
is rebuilt using cached layers to match this checkout. Network trials use fresh results directories and open the
generated timeline when a desktop viewer is available. Stage 5 always runs its
tests and reports when live SDN is unavailable. Stage 6 reads the retained
180-outcome evaluation, clearly labelled with its earlier measurement scope.
Stage 7 runs the complete current test suite. Stage 8 runs the browser console
until Ctrl-C returns to the menu.

For a single non-interactive stage use
`python3 scripts/run.py interactive --step 1`.
The alias `python3 scripts/run.py menu` opens the same menu. Some network tests
and static failures take longer than a ten-minute presentation, so rehearse and
select the stages needed for the assessment.


## Live telemetry console

Run the console from the repository root. It builds the C binaries and opens the browser.

```sh
python3 scripts/run.py viz
```

Choose transport flags and click **Run Live C Transfer**. The console captures actual
24-byte headers through a UDP relay, streams sender/receiver JSONL records, shows
the sender ring snapshots, and reports independent SHA-256 verification. The relay
adds 15 ms in each direction to make the transitions visible. **Drop next DATA**
discards one observed DATA datagram.

Load a trial from the selector or enter a directory under results/ and select
**Tail active trial** for a running Mininet experiment. Replay preserves recorded
monotonic timing with play, pause, single-step and speed controls. Older recordings
supply only the fields they retained. The localhost run supplies transport data,
while Mininet recordings supply controller events.


Run the localhost examples from the repository root in a Linux shell. Each receiver exits after one upload.

## Transfer under loss

```sh
make
dd if=/dev/urandom of=sample.bin bs=1024 count=256
./server 9000 out.bin & receiver=$!
sleep 0.2
./client --host 127.0.0.1 --port 9000 --file sample.bin --sack --adaptive-rto --cc --drop-rate 0.10 && wait "$receiver" && cmp sample.bin out.bin
sha256sum sample.bin out.bin
```

Show the matching digests and the sender’s retry count. Simulated loss applies to outgoing DATA attempts.

## Two simultaneous uploads

```sh
./server 9000 out0.bin & r0=$!
./server 9001 out1.bin & r1=$!
sleep 0.2
./client 127.0.0.1 9000 sample.bin & c0=$!
./client 127.0.0.1 9001 sample.bin & c1=$!
wait "$c0" && wait "$c1" && wait "$r0" && wait "$r1" && cmp sample.bin out0.bin && cmp sample.bin out1.bin
sha256sum sample.bin out0.bin out1.bin
```

Each process owns one port and one destination file.

## OpenFlow 1.3 failover and static contrast

Build the image once. Use fresh output directories for each rehearsal.

```sh
docker build -t rudp-lab .
run_dir="results/demo-$(date +%Y%m%d-%H%M%S)"
for mode in failover static; do
  docker run --rm --privileged -v "$PWD/results:/project/results" rudp-lab python3 scripts/run.py demo --mode "$mode" --output "$run_dir/$mode" || break
done
find "$run_dir" -name timeline.svg
```

Open the failover trial’s timeline.svg in a browser. Point to link down, alternate route ready and the first ACK that advances the contiguous file prefix. The output hash must match. In static mode the route stays on the failed branch and the transfer fails as expected. Prepare the static run before the presentation to avoid waiting for retry exhaustion.
