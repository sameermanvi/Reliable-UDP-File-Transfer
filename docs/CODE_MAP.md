# Code map for review and viva

Read ARCHITECTURE.md for state/packet details and DESIGN_DECISIONS.md for why.

| Location | Entry point | Responsibility |
| --- | --- | --- |
| `src/packet.h` | constants, packet types | 24-byte wire header, 1024-byte chunks, 32-slot bound |
| `src/client.c` | `main` → `exchange` → `send_file` | Metadata/negotiation, reliable DATA, explicit FIN |
| `src/client.c` | `send_file` send loop | Sequence span and CWND jointly bound outstanding sends |
| `src/client.c` | `send_file` ACK block | Validate SACK before state changes; mark coverage and collect clean RTT samples |
| `src/client.c` | `gap_reports` / `fast_sent` | Three distinct later ACKs trigger one fast retry; timeout remains the fallback |
| `src/server.c` | `data_ack`, `main` | Buffer reordered DATA, drain the contiguous prefix, send ACK/bitmap |
| `src/server.c` | FIN handling | Verify size/CRC, close and rename temporary output; re-ACK duplicate FIN |
| `src/utils.c` | `packet_encode`, `packet_decode` | Explicit network-order serialization and CRC/length validation |
| `src/utils.c` | `receive_packet`, `send_packet` | UDP socket operations and bounded receive wait |
| `controller/routing.py` | `PathPolicy.choose` | Exclude hard failures; prefer materially better fresh health |
| `controller/probes.py` | `ProbeTracker` | Validate independent branch probes, expire losses, smooth directional samples |
| `controller/failover.py` | `_monitor`, `port_status`, `_reconcile`, `barrier_reply` | Probe scheduling, hard-failure events, rule installation and readiness |
| `scripts/run_experiments.py` | `run_trial`, `recovery_metrics` | Inject faults, verify endpoint/hash outcomes and join recovery events |
| `scripts/evaluate.py` | `linux_plan`, `main` | Run tests and repeated matrix; save manifest and plots |

## Follow one transfer

1. START advertises file length and CRC and negotiates ACK format.
2. Sender fills available ring slots. A slot is retained until ACKed coverage lets
   the contiguous base move past it; modulo indexing reuses bounded memory.
3. Receiver accepts only the active peer/session, buffers in-window chunks and
   writes the contiguous prefix once. Duplicate DATA does not rewrite bytes.
4. Missing DATA is retried on timeout or distinct later-ACK gap evidence. Karn's
   rule excludes ambiguous retransmitted RTT samples. Optional CWND reacts to loss.
5. Independently, SDN excludes a failed path or changes path on probe health.
   Rule barriers mark route readiness; later contiguous ACK advancement marks
   application recovery. Both events are required for the measured recovery.
6. FIN completes only after size/CRC validation and successful output finalization.
   The harness compares independent SHA-256 digests before deleting payloads.

## Script entry points

- `setup_env.sh`: native Ubuntu 22.04 packages, Python environment and OVS setup.
- `container_entrypoint.sh`: private container OVS database/daemon startup.
- `demo.py`: one short scenario; `--help` lists static, reverse and soft variants.
- `evaluate.py`: at least three repeats; `--local-only` and `--plan-only` remain available.
- `benchmark_reliability.py`: localhost impairment proxy and transport/CC ablations.
- `run_experiments.py`: explicit Linux scenario/transport matrix controls.
- `plot_metrics.py`, `plot_timeline.py`: summaries and joined event plots.
- `start_controller.sh`, `start_topology.sh`: manual lab operation.

For each public script use `--help` where supported. Do not edit retained evidence
or reuse a nonempty output directory. Runtime traces are observability required
for verification, not leftover debug output.
