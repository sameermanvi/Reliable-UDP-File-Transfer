# Measurements

The `evaluation-2026-10-29` and `concurrent-2026-10-29` directories are historical
measurements restored with implementation `49f9ae6`; their environment records
and source fingerprints describe those runs. They are not new measurements.

The newer `validation` directory is retained as evidence for the simplified
revision. Do not combine it with restored-protocol results.

Generate fresh measurements using `scripts/run_experiments.py` and graphs using
`scripts/plot_metrics.py`, as described in the main README.


Final rubric evidence (31 October):
- `rubric-final-native/`: passing 48-test log, three-repeat 60-transfer local
  ablation matrix with hashes, summaries and plots. No final SDN runtime claim.
- `rubric-integration-history/`: unchanged extracted 29 October events and a
  regenerated joined timeline, with archive/source provenance.
- `rubric-linux-plan/`: pending execution command plan and unavailable-daemon
  evidence. This directory contains no measured final Linux trials.

Generate the final network bundle with
`sudo .venv/bin/python scripts/evaluate.py --output results/rubric-final`.
Do not merge numbers from different source fingerprints into one comparison.
