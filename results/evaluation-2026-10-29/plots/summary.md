# Experiment summary

All rows are retained. Rates include failures; numeric performance summaries use successful transfers only. N/A is not zero. Multiple flows in one trial share a network and are not independent trials.

| Scenario | Mode | Trials | Successful flows | Expected outcomes | Mean goodput (Mb/s) | Mean recovery (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| normal | static | 3 | 3/3 | 3/3 | 9.2173 | N/A |
| normal | failover | 3 | 3/3 | 3/3 | 9.2167 | N/A |
| loss | static | 3 | 3/3 | 3/3 | 1.3280 | N/A |
| loss | failover | 3 | 3/3 | 3/3 | 1.3003 | N/A |
| link-failure | static | 3 | 0/3 | 3/3 | N/A | N/A |
| link-failure | failover | 3 | 3/3 | 3/3 | 8.7240 | 0.1972 |
