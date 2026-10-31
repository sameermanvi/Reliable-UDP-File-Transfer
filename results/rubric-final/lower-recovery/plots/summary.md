# Experiment summary

All rows are retained. Rates include failures; numeric performance summaries use successful transfers only. N/A is not zero. Multiple flows in one trial share a network and are not independent trials.

| Scenario | Mode | Trials | Successful flows | Expected outcomes | Mean goodput (Mb/s) | Mean recovery (s) | Censored |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| link-failure | failover/adaptive/bitmap/cc=off/loss=0.0/fail=1/flap=1/start=lower/cut=lower/reorder=0/degrade=0 | 3 | 3/3 | 3/3 | 9.2453 | 0.0449 | 0 |
