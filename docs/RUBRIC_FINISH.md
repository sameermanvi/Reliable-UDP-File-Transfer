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

Verified complete for steps 1–5: final Linux Docker evaluation passed 48 tests
and all 180 trial expectations across three repeats (132 hash-matched successes,
48 expected static failures). Both initial branches recover; probe soft degradation
and loss/reordering/flaps pass. All 57 recovered trial rows have event-supported
link_down → route_ready → useful contiguous ACK advancement. Censored and
not-applicable measurements remain null. See [verification](VALIDATION.md#final-linux-docker-validation--verified-31-october-2026)
and [manifest](../results/rubric-final/evaluation.json).

This closes the final Mininet/userspace OVS evidence gap on the Ubuntu 22.04
container inside the Ubuntu 26.04 ARM64 VM. It does not validate kernel OVS.
Step 6 evidence status is synchronized in README, VALIDATION, KEY_RESULTS and
this checklist only; other listed documents were not re-audited or changed.
Step 7's existing historical indexing is preserved; the entire final evaluation
bundle is retained without changing .gitignore. Preflight is excluded from the
final bundle counts.

Retained transport upgrade files from the preceding implementation are also part
of the final diff: `src/server.c` (bitmap negotiation/ACKs and receiver events),
`src/utils.c`/`src/utils.h` (wire decoding and JSONL helper), `src/packet.h`
(extension packet types), and `tests/test_local.py` (explicit legacy peer and
rich-event filtering). They were audited and exercised by the final suite rather
than rewritten. `scripts/demo.py` was replaced with a thin assessed-runner wrapper.
