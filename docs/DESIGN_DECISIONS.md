# Design decisions

| Choice | Benefit for the assessed project | Accepted cost / limit |
| --- | --- | --- |
| C/POSIX UDP and one event loop | Socket mechanics, ACKs and retries are explainable | Single upload per receiver; no shared service |
| Selective Repeat, 32 slots | Buffer later packets; retry only missing coverage; bounded memory | Head holes limit sequence span; high bandwidth-delay paths can underfill |
| 32-bit bitmap plus cumulative base | Repeated receiver state repairs lost ACK information in eight payload bytes | One bitmap revision, explicit opt-in START types, no automatic downgrade |
| Adaptive RTO + Karn + backoff | Avoid repeated premature retries on slow paths; reject ambiguous RTTs | Initial 200 ms may still be too short; 50–2000 ms lab bounds |
| Three distinct later ACKs | Fast gap recovery without a new DATA format | Reordering may trigger a needless retry; no full TCP recovery |
| Capped slow start / additive increase | Basic sender response to loss | Short uncontended flows get slower; fairness is unproven |
| Same monotonic clock | Join application behavior to link-down and rule readiness | Only comparable on the same kernel |
| Bidirectional branch probes | Measure the idle backup and soft degradation without changing UDP | Probe loss is noisy; control-channel latency contributes; small extra traffic |
| EWMA, freshness, score threshold, hold-down | Avoid routing on stale/small transient differences | Soft detection deliberately slower than hard failure |
| Hard failures override health | A live but unhealthy route is preferable to a broken one | If neither branch works, retries cannot manufacture connectivity |
| Independent SHA-256 and atomic rename | Strong experimental correctness evidence; failed transfer preserves destination | CRC-32 itself is not authentication; rename is not power-loss durability |
| CC off in the main matrix | Isolate routing, RTO and ACK format effects | CWND behavior is verified and separately ablated, not a fairness claim |

No full TCP clone, encryption/authentication, FTP compatibility, persistent resume,
web frontend or unrelated feature was added. TCP is the right production default;
this lab exposes reliable datagram state and its interaction with SDN forwarding.
The fixed timer, plain ACKs and static route are meaningful controlled baselines,
not deliberately broken implementations.

Wire and estimator details: ARCHITECTURE.md. Implementation navigation: CODE_MAP.md. Claims and their artifacts: REPORT.md and VALIDATION.md.

Probe timing: a 250 ms send interval tracks both branches with about 16 frames/s;
a 500 ms deadline tolerates delayed replies. Four fresh samples reduce premature
health decisions; the 2 s hold-down limits soft-route oscillation. These are lab
tradeoffs, not universally optimal settings. Recovery requires contiguous ACK
advancement after route barriers so duplicate ACKs do not count as progress.
