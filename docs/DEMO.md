# Live demonstration

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
