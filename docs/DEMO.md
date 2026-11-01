# Live demonstration

The validated route is Ubuntu 22.04 Docker with userspace OVS (Docker command below).
Native setup targets Ubuntu 22.04; newer Python versions may not support the pinned
Eventlet dependency. Use a prepared **Linux** host with Mininet, OVS and OS-Ken. From the repository:

```sh
sudo sh scripts/setup_env.sh                 # setup once; needs package access
make test                                   # preflight before the presentation
sudo .venv/bin/python scripts/run.py demo --mode failover --output results/live-failover
```

The command owns topology/controller/endpoint startup and cleanup. It:
1. Starts OS-Ken in failover mode, connects the diamond, waits for route_ready
   and verifies host connectivity.
2. Starts an 8 MiB C transfer and waits for actual contiguous ACK progress.
3. After 0.5 s of progress, takes the active branch's s1 link down permanently.
4. Prints LINK DOWN, ROUTE READY on the alternate, completion, recovery latency
   and `sha256_match=True`. No application restart and no primary-link restoration.

Say: “The controller restores reachability; Selective Repeat recovers missing
chunks. These are separate events within the same upload.”

Open the trial's `plots/timeline.svg`: red link_down, green route_ready, purple
first useful post-route ACK. Open root `metrics.csv` for source/output SHA-256,
recovery measurements and success. The console prints the result directory;
each trial retains `controller.jsonl`, `progress-0.jsonl`, `receiver-0.jsonl`,
endpoint logs, `outages-0.json`, and initial/final flow and queue dumps.
`success=True`, `sha256_match=True`, and `expectation_met=True` are all required.

## Static contrast and robustness (ready, not all needed live)

```sh
sudo .venv/bin/python scripts/run.py demo --mode static --output results/live-static
sudo .venv/bin/python scripts/run.py demo --initial-path lower --output results/live-lower
sudo .venv/bin/python scripts/run.py demo --scenario robust --output results/live-robust
sudo .venv/bin/python scripts/run.py demo --scenario soft-degradation --mib 16 --output results/live-soft
```

Static contrast keeps the broken branch: no alternate route_ready, client fails,
receiver times out, no finalized output. `expectation_met=True` means the expected
failure was observed, not that the transfer succeeded. Adaptive retry exhaustion
can take about a minute; have this run recorded before presenting if time is tight.
Lower-initial proves lower→upper recovery. Robust combines loss, host reordering
and repeated short primary flaps. Soft degradation adds loss without taking a
link down; probe scores must cause a health_update route change.

Use fresh output directories. Keep the input large enough for injection; a trial
that finishes too early is rejected. If failure timing or resources invalidate a
run, show the error and rerun; never call an uninjected run successful failover.

Docker alternative after starting Docker Desktop/Engine:

```sh
docker build -t rudp-lab .
docker run --rm --privileged -v "$PWD/results:/project/results" rudp-lab python scripts/run.py demo --mode failover --datapath user --output results/live-failover
```

## Retained evaluation

The completed three-repeat Linux Docker/userspace OVS evaluation met 180/180
expectations. See [Key Results](KEY_RESULTS.md) and [validation](VALIDATION.md).
Do not run the full matrix during a ten-minute presentation.

For a new full run use a fresh output directory:

```sh
docker run --rm --privileged -v "$PWD/results:/project/results" rudp-lab python scripts/run.py evaluate --output "results/evaluation-$(date +%Y%m%d-%H%M%S)"
```

## Ten-minute assessment sequence

1. Explain the two independent responsibilities: UDP reliability and SDN routing.
2. Show the diamond in ARCHITECTURE.md, then run one failover demo.
3. Point out initial route, injected link-down, alternate route readiness,
   hash-matched completion, and the joined timeline.
4. Show KEY_RESULTS.md for static contrast and repeated measurements.
5. Use CODE_MAP.md to locate the requested implementation; VIVA.md gives the
   design rationale. Keep a retained final timeline available if live setup fails.

The console's `recovery=` is injection-to-progress, not link-down-to-progress.
The CSV and joined events distinguish both. Never label a startup failure or
uninjected transfer as successful failover.
