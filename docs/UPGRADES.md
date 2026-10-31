# Upgrade index

The final scope follows the official 40-mark rubric.

- Exact prioritized file changes: [RUBRIC_FINISH.md](RUBRIC_FINISH.md).
- Final packet format, negotiated bitmap revision, timers, probes and recovery:
  [ARCHITECTURE.md](ARCHITECTURE.md).
- Why these choices and their costs: [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md).
- Measured results and plot list: [KEY_RESULTS.md](KEY_RESULTS.md).
- Full repeated evaluation: `sudo .venv/bin/python scripts/evaluate.py --output results/rubric-final`.
- One-page live sequence and static contrast: [DEMO.md](DEMO.md).
- What has actually run: [VALIDATION.md](VALIDATION.md).

Final local evidence is in results/rubric-final-native. Earlier exploratory
reliability-local/reliability-final runs and the older reliability-verified bundle
are not the final validation. Historical Mininet evidence remains identified by
its original source fingerprint and does not validate the new probe controller.
