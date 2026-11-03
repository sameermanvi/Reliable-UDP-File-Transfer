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


## Guided browser demonstration

```sh
python3 scripts/run.py viz
```

Choose 1 for a clean 32 KiB transfer, 2 or 3 for the same first-attempt losses
at packets 4, 14 and 23, or 4 to compare both modes on identical bytes.
The C endpoints run first. Guided playback merges their events and relay frames
by timestamp. Blue means sent, amber means buffered, and green means the client
has acknowledged the contiguous prefix. Each card keeps its original ID.
Scenario 5 replays a measured Mininet failover. For longer files the board
shows the first 32 packets while the counters cover the entire transfer.

Use Viva Smart for a guided walkthrough, Step-by-step to stop at losses and
retries, or Instant to reach the result. Click a story entry to inspect its
packet states. Playback speed is independent of the measured transfer duration.

Raw logs, wire bytes, manual transport settings and active-trial tail controls are
inside the collapsed advanced drawer. Pause a red gap, amber buffered chunk or
route change and read the scenario's three talking points.


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

## Four-person ten-minute presentation

Use this as an ownership and rehearsal plan. Attribute implementation work to its actual authors.

| Presenter | Time | Scenario | What to say and point to |
| --- | --- | --- | --- |
| 1 — Sender and reliability | 0:00–2:00 | 1, then 2 | “UDP gives us datagrams. Our sender adds sequence numbers, a bounded 32-slot window and retransmission. A missing ACK holds the contiguous base.” Point to a missing slot and the timer. |
| 2 — Receiver and integrity | 2:00–4:00 | 3 | “The receiver saves later chunks instead of discarding them. SACK reports which chunks are already buffered. Once the hole is repaired, the contiguous prefix advances. CRC32 checks the file before finalization and independent SHA-256 verifies it.” Point to amber slots, the bitmap and MATCH. |
| 3 — SDN control | 4:00–7:00 | 5 | “The application cannot repair a broken path. OpenFlow port status detects the hard cut. The controller installs the lower branch and waits for barriers. Separate bidirectional probes detect soft degradation and assess the backup.” Pause on LINK DOWN and ROUTE READY. |
| 4 — Integration and evidence | 7:00–9:00 | CLI stage 6, then web preset 4 | “A static route cannot deliver through a permanent cut. The recorded matrix contains 132 hash-matched transfers and 48 expected static failures. This A/B pair is a separate live comparison.” Point to the failure outcome and measured comparison bars. |
| All — Questions | 9:00–10:00 | Pause | Each person answers for the module they reviewed. Every member should be able to trace START → DATA/ACK → FIN and link down → route ready → useful ACK. |

Prepare the recorded traces and A/B results before the assessment so selection and
playback fit the time limit. Scenario 4 runs actual transfers and can take longer
under random loss. Nobody should promise a particular speedup or recovery time.

For the graphs, explain the labelled measurement interval before quoting a number.
The recovery title gives link-down to the first useful ACK after route readiness.
The separate timestamp rows resolve markers that overlap at full-run scale.
The congestion trace is the project's UDP congestion window. It does not measure
TCP fairness or establish the behavior of a TCP implementation.
