# Rubric completion plan (priority order)

1. Transport correctness — `src/client.c`, `src/packet.h`, `tests/test_transport.py`,
   `tests/test_protocol.py`, `Makefile`: exact RUDP_RTO switch; validate all SACK
   coverage before mutation; retain explicit v1 extension negotiation; exercise
   malformed ACKs, unknown versions, Karn, timer bounds and retry behavior.
2. Socket–SDN measurement — `scripts/run_experiments.py`, `scripts/plot_timeline.py`,
   `tests/test_metrics.py`: path-independent recovery, censored observations,
   link-down → barrier-ready → useful prefix advancement; bound repeated events.
3. Dynamic SDN — `controller/probes.py`, `controller/failover.py`,
   `controller/routing.py`, `tests/test_controller.py`, `tests/test_probes.py`, `tests/test_openflow.py`:
   independently probe both branches; EWMA loss/latency, freshness, hysteresis;
   hard-down availability takes priority; log observations and every route decision.
4. Robust scenarios — `scripts/run_experiments.py`, `mininet/link_impairment.py`:
   permanent active-route failure, lower-to-upper recovery, primary flaps, combined
   loss/reordering/flaps, and primary soft degradation with no link-down event.
5. Evaluation — `scripts/evaluate.py`, `scripts/plot_metrics.py`,
   `scripts/benchmark_reliability.py`, `scripts/demo.py`: one entry point for tests, three-repeat
   routing/RTO/ACK/loss/failure-time matrix, tables, plots and joined timelines.
   Every successful transfer needs endpoint success plus SHA-256 and size equality.
6. Submission evidence — `README.md`, `docs/ARCHITECTURE.md`,
   `docs/DESIGN_DECISIONS.md`, `docs/VALIDATION.md`, `docs/REPORT.md`,
   `docs/VIVA.md`, `docs/DEMO.md`, `docs/KEY_RESULTS.md`, `docs/RUBRIC_MAPPING.md`:
   synchronize final semantics; concise viva; one-page live sequence and static
   contrast; distinguish executed artifacts from pending Linux integration.

No frontend, new transport, or unrelated feature is in scope. Existing historical
results retain their original source identity; they do not validate new probes.

7. Result indexing — `.gitignore`, `results/README.md`: retain final native,
   historical-integration and pending-Linux-plan bundles; keep historical source
   identities intact. `scripts/plot_timeline.py` marks first useful post-route ACK.

Implemented and locally verified: steps 1–2 analysis, probe/policy/handler logic,
scenario/evaluation/demo code and documentation. Executed: 48 local tests and 60
hash-verified local transfers. Pending: final real Mininet/OVS runs for steps 2–5.

Retained transport upgrade files from the preceding implementation are also part
of the final diff: `src/server.c` (bitmap negotiation/ACKs and receiver events),
`src/utils.c`/`src/utils.h` (wire decoding and JSONL helper), `src/packet.h`
(extension packet types), and `tests/test_local.py` (explicit legacy peer and
rich-event filtering). They were audited and exercised by the final suite rather
than rewritten. `scripts/demo.py` was replaced with a thin assessed-runner wrapper.
