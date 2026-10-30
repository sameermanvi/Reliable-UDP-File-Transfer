# Demo and experiment guide

Run commands from the repository root on a dedicated Linux lab machine or VM.
The setup installs Mininet/Open vSwitch and a Python environment for the SDN
controller. Keep the generated environment and run logs with the experiment
record.

## Preparation

```sh
sudo bash scripts/setup_env.sh
make -C src test
python3 tests/test_controller.py
python3 tests/test_metrics.py
```

Confirm that the protocol and controller tests pass before introducing network
impairments. The C application and pure controller tests can run on macOS, but
the lab steps below need Linux.

## Manual topology demo

Open a controller terminal:

```sh
mkdir -p results/manual
RUDP_MODE=failover RUDP_EVENT_LOG="$PWD/results/manual/controller.jsonl" \
  .venv/bin/osken-manager --ofp-tcp-listen-port 6653 controller/failover.py
```

Open a second terminal and start the topology:

```sh
sudo .venv/bin/python mininet/topology.py \
  --bandwidth 10 --delay 5ms --loss 0 --controller-port 6653
```

At the Mininet prompt, inspect connectivity and the selected route:

```text
nodes
net
pingall
sh ovs-ofctl -O OpenFlow13 dump-flows s1
sh ovs-ofctl -O OpenFlow13 dump-flows s4
```

The initial route is `h1–s1–s2–s4–h2`. Bring down an upper-path link, inspect the
rules again and check connectivity:

```text
link s1 s2 down
sh ovs-ofctl -O OpenFlow13 dump-flows s1
sh ovs-ofctl -O OpenFlow13 dump-flows s4
pingall
link s1 s2 up
```

In failover mode, the selected path changes through `s3`. Restoring the original
link leaves the working alternate path selected. Repeat with `RUDP_MODE=static`
in a fresh lab session to show that static rules retain the failed upper path.
Exit Mininet and stop the manual controller before running the automated lab.

## Transfer and failure demo

The runner manages the controller, hosts and endpoint processes so the failure
occurs while DATA is being transferred. Use its logs and integrity checks as the
file-transfer evidence; a successful ping alone is insufficient.

```sh
sudo .venv/bin/python scripts/run_experiments.py \
  --scenarios link-failure --modes static failover \
  --repeats 1 --output results/demo
```

Present the input size and hash, initial upper-path event, link-down event,
alternate route event, resumed transfer progress, endpoint exit status and final
output hash. The static transfer is expected to fail after bounded retries. The
failover transfer is expected to finish if route recovery occurs within the
application's retry budget. An unexpected failure should remain in the results.

## Repeated evaluation

```sh
sudo .venv/bin/python scripts/run_experiments.py \
  --scenarios normal loss link-failure --modes static failover \
  --repeats 3 --file-size 4194304 --bandwidth 10 --delay 5ms \
  --loss 2 --output results/evaluation
.venv/bin/python scripts/plot_metrics.py results/evaluation/metrics.csv \
  --output results/evaluation/plots
```

Keep bandwidth, delay, file size and requested loss the same when comparing
routing modes. The `loss` scenario applies the requested loss setting; normal
and link-failure cases isolate their own conditions. Repeat trials because
network scheduling and random loss can vary. Use a new output directory for
each evaluation set so earlier evidence remains available.

Independent transfers can share the topology:

```sh
sudo .venv/bin/python scripts/run_experiments.py \
  --scenarios normal link-failure --modes static failover \
  --flows 2 --repeats 3 --output results/concurrent
```

Each flow has its own client, receiver, port and output. This demonstrates
concurrent flows without claiming a single receiver serves several users.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `mininet` cannot be imported | Use the `.venv` interpreter created by setup; it includes the system Mininet package |
| Open vSwitch connection fails | Confirm the Open vSwitch service is running on the Linux host |
| Controller address is already in use | Stop a previous lab controller before starting another experiment |
| Hosts cannot communicate before failure | Check controller logs, switch connections and OpenFlow 1.3 flow tables |
| Transfer finishes before link injection | Use a larger file or lower bandwidth and retain the runner's failure diagnosis |
| Transfer times out after switching | Inspect outage duration, controller events, endpoint logs and retry counts |
| Old Mininet interfaces remain after an interrupted run | On the dedicated lab host, run `sudo mn -c` before starting a new lab |

Do not run cleanup against a machine hosting someone else's active Mininet
experiment. Keep failed-run logs before retrying. The topology accepts
`--datapath user` for Linux environments using the Open vSwitch userspace
datapath; record this choice because its performance can differ from the
default kernel datapath.

## Viva points

Be ready to explain why individual ACKs and receiver buffering permit selective
retransmission, how lost ACKs create harmless duplicates, why FIN is needed, and
why CRC-32 is not authentication. Explain that the application preserves the
transfer state while the controller changes network forwarding. Distinguish
controller rule readiness from resumed application progress, and explain why
static-route failure is a useful baseline rather than a reliable-UDP defect.
