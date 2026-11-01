# Progress and protocol event logs

Each endpoint can set `RUDP_PROGRESS_LOG` to its own fresh path. Creation is
exclusive; records flush immediately. Logging failures fail the process. Do not
reuse a path across processes. Monotonic nanoseconds are comparable across Linux
Mininet namespaces on the same kernel, not across physical machines.

`ack_progress` retains `base`, `bytes`, `monotonic_ns` and includes `transfer_id` for joining.
Other records contain `event`, `monotonic_ns`, hex `transfer_id`, `sequence`,
`base`, numeric `value`, and `reason`:

| Event | Value / interpretation |
| --- | --- |
| send | Slot RTO in ms; original DATA |
| retransmit | Slot timeout in ms; reason timeout or fast_gap |
| ack_received | Bitmap numeric value, or zero for individual ACK |
| window_advance | Current cwnd; contiguous prefix advanced |
| rto_update | Global RTO ms; rtt_sample or timeout_backoff |
| srtt_update | Smoothed RTT ms |
| cwnd_change | Congestion window in packets; initial/new_ack/timeout/fast_gap |
| loss_detected | Expired timer ms or distinct later-ACK count |
| out_of_order / gap_detected | Receiver arrival above missing base |
| hole_filled | Receiver base arrival unlocks buffered suffix |

`ack_received` logs valid ACK arrivals, including duplicates; only new coverage
trains congestion growth and gap evidence. Receiver logs belong to its own file.
The sender's gap reasoning can therefore be checked against actual receiver state.

Join with controller link_down, path_health, route_installing and route_ready
records using `scripts/commands/plot_timeline.py`. Red dashed markers are link-down;
green dashed markers are barrier-confirmed readiness. A later ACK is progress
observed after switching, not proof of which physical path carried that ACK.
Use final hash verification and retain raw logs alongside plots.

Controller `probe_result` records path, direction, success, elapsed delay_ms and
monotonic_ns. `path_health` includes fresh branch scores and directional sample
counts; scores combine EWMA loss and latency and are not pure loss rates.
`route_decision` records previous/selected path, cause and scores; suppressed
soft moves report hold_down_or_barrier. `route_installing` and `route_ready`
carry generation and path. Invalid sender reports emit ack_rejected/invalid_sack.

Recovery JSON includes failure, observed-link-down, route-ready and useful-ACK
nanoseconds plus the component intervals and recovered/censored/inactive status.
The primary reported latency is observed link_down to useful ACK; injection-to-ACK
is a separate metric. Strictly later prefix progress is required after route_ready.
