# Reliable UDP File Transfer with SDN Failure Recovery

## Objective

Transfer binary files correctly over UDP while an SDN controller detects a link
failure and moves the active transfer to another path. The application supplies
ordering, acknowledgments, retransmission, duplicate suppression and integrity
checks. Mininet supplies the controlled network and OS-Ken programs its switches.

## Implementation

The C sender keeps up to 32 chunks in flight. Each chunk carries a sequence
number and CRC-32. The receiver buffers out-of-order chunks and acknowledges
individual packets. A missing acknowledgment triggers a retry after 200 ms;
30 retries bound the time spent on an unreachable peer. START declares the file
size and CRC, and FIN completes the upload only after the receiver verifies both.
The output is installed using a temporary file and rename.

The network has two hosts and four OpenFlow 1.3 switches. Both branches have the
same configured bandwidth and delay. The controller initially chooses the upper
branch. Port-status events identify a failed link. In failover mode the controller
updates both host ingress rules to select the lower branch and waits for switch
barrier replies before recording route readiness. Static mode retains its
original route. See [architecture](ARCHITECTURE.md) for ports and packet fields.

## Experimental method

Run the same file and transport implementation with both routing policies under
three conditions: normal operation, configured random packet loss, and failure
of link s1–s2 during an active transfer. Use at least three repetitions. The
runner waits for every client to acknowledge data before starting the failure
timer, checks that all clients are still running, and rejects trials in which
the file finished before the intervention.

The default file is 4 MiB, each inter-switch link is limited to 10 Mb/s, and each
inter-switch egress has 5 ms delay. The loss case configures 2% loss on each
inter-switch egress, including the reverse direction; this is not a measured
end-to-end loss rate. Loss is enabled after initial connectivity is verified and
before either endpoint starts. The file generator is seeded, but Linux netem loss draws
and process scheduling vary between trials. Repetitions quantify that variation.

The client/server pair is held constant in the static/failover comparison.
This isolates routing policy; it is not a speed comparison with FTP or TCP.
Concurrent trials use independent clients and receiver processes on separate
ports. Their observations share a network and must not be counted as independent
repetitions when discussing statistical confidence.

## Metrics and evidence

| Metric | Definition |
| --- | --- |
| Completion | Both endpoints exit successfully and the final SHA-256 and file size match |
| Payload goodput | Original file bits divided by START-to-FIN_ACK time; excludes metadata scan and receiver linger |
| Retransmissions | Extra DATA sends by the client; ACK loss can also cause these, so they are not a packet-loss estimate |
| Route installation time | Time from the failure command request to the controller's lower-path `route_ready` event |
| Progress recovery time | Time from the failure command request to the first new contiguous ACK progress after lower-path readiness |
| ACK gap | Time from the last progress before failure to the first progress counted as recovered |
| Expected outcome | Normal/loss and failover trials complete; static link-failure trials exhaust DATA retries and the receiver times out without installing output |

All experiment timestamps use `CLOCK_MONOTONIC` on the same Linux system.
Failure-command start/end timestamps expose the intervention duration. OpenFlow
barriers show that flow modifications were processed, not that every packet
was forwarded. The progress log and final integrity check provide application
evidence. Recovery is an observed progress interval, not a measurement of an
individual packet's latency.

Keep `environment.json`, `metrics.csv`, `metrics.json`, controller logs, progress
logs and endpoint logs. The environment record includes a fingerprint of the
measured source files. `scripts/plot_metrics.py` generates completion, goodput,
retransmission and recovery figures plus a summary table. Performance means and
min–max ranges use successful flows; completion rates include every trial.
Unavailable measurements remain N/A rather than being converted to zero.

## Results

The completed evaluation met all 18 expected outcomes. Each cell below uses
three independent trials; goodput averages use successful transfers only.

| Scenario | Static completion | Failover completion | Static goodput (Mb/s) | Failover goodput (Mb/s) |
| --- | --- | --- | ---: | ---: |
| Normal | 3/3 | 3/3 | 9.217 | 9.217 |
| 2% loss per egress | 3/3 | 3/3 | 1.328 | 1.300 |
| Link failure | 0/3 (expected) | 3/3 | N/A | 8.724 |

Failover restored contiguous ACK progress in 0.1952–0.1995 s (mean 0.1972 s).
All successful outputs matched SHA-256. A separate two-flow link-failure trial
also completed both files, each at 4.540 Mb/s; these two flows share one trial.
The loss results show the cost of retransmission with the fixed window and
retry timer. Similar normal goodput reflects the identical active path before
failure. Three repetitions support this demonstration, not broad statistical
claims about other networks.

See [summary and plots](../results/evaluation-2026-10-29/plots/summary.md),
[concurrent results](../results/concurrent-2026-10-29/metrics.csv), and
[validation](VALIDATION.md). Raw evidence is packaged in each result directory.

## Limits and discussion

The controller knows this diamond's port map; arbitrary topology discovery,
congestion-aware routing, encryption, authentication and restart/resume are
outside this implementation. CRC-32 detects accidental errors and does not
authenticate a sender. A fixed window and timer do not provide adaptive
congestion control. Outages beyond the retry budget can still fail a transfer.

The userspace OVS datapath used in Docker differs from the kernel datapath on a
native Linux host. CPU scheduling, virtualization and progress-log I/O affect
timing. Report the actual environment and repeat on the assessment machine.
Each receiver process accepts one upload; concurrent experiments do not turn it
into a shared multi-client file service.
