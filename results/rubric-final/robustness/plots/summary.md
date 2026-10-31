# Experiment summary

All rows are retained. Rates include failures; numeric performance summaries use successful transfers only. N/A is not zero. Multiple flows in one trial share a network and are not independent trials.

| Scenario | Mode | Trials | Successful flows | Expected outcomes | Mean goodput (Mb/s) | Mean recovery (s) | Censored |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| robust | failover/adaptive/bitmap/cc=off/loss=2.0/fail=1/flap=0.5/start=upper/cut=upper/reorder=20.0/degrade=0 | 3 | 3/3 | 3/3 | 4.1797 | 0.0196 | 0 |
| robust | failover/adaptive/bitmap/cc=off/loss=2.0/fail=1/flap=2.0/start=upper/cut=upper/reorder=20.0/degrade=0 | 3 | 3/3 | 3/3 | 4.1267 | 0.0383 | 0 |
| soft-degradation | failover/adaptive/bitmap/cc=off/loss=0/fail=1/flap=0.5/start=upper/cut=upper/reorder=0/degrade=35 | 3 | 3/3 | 3/3 | 8.6330 | N/A | 0 |
