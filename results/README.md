# Retained evidence

| Bundle | Scope |
| --- | --- |
| [rubric-final](rubric-final/evaluation.json) | Final Linux Docker/userspace OVS: 180 expectations, 132 hash-matched successes, 48 expected static failures; three repeats |
| [rubric-final-native](rubric-final-native/evaluation.json) | Final macOS transport evaluation: 48 tests and 60 hash-matched transfers; includes CC comparisons |
| [archive](archive/README.md) | Superseded experiments, old example and execution plans; provenance only |

Raw final logs are intentionally retained unchanged for audit. Their millions of
JSONL events are generated data, not implementation code. Start with
[Key Results](../docs/KEY_RESULTS.md) and the aggregate CSVs, then open per-trial
timelines/events when needed. Do not rerun into these directories.

These bundles identify the measured source/runtime. Later documentation and
comment-only cleanup does not constitute a new measured Linux run. Hash equality
uses recorded input/output digests; the runner did not retain file payloads.
