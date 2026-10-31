# Experiment summary

All rows are retained. Rates include failures; numeric performance summaries use successful transfers only. N/A is not zero. Multiple flows in one trial share a network and are not independent trials.

| Scenario | Mode | Trials | Successful flows | Expected outcomes | Mean goodput (Mb/s) | Mean recovery (s) | Censored |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| local-delay | localhost/fixed/plain/cc=off/loss=0/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 14.9880 | N/A | 0 |
| local-delay | localhost/adaptive/plain/cc=off/loss=0/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 15.1267 | N/A | 0 |
| local-delay | localhost/fixed/bitmap/cc=off/loss=0/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 14.9800 | N/A | 0 |
| local-delay | localhost/adaptive/bitmap/cc=off/loss=0/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 15.1440 | N/A | 0 |
| local-delay | localhost/adaptive/bitmap/cc=on/loss=0/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 6.7517 | N/A | 0 |
| local-faults | localhost/fixed/plain/cc=off/loss=deterministic/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 11.2360 | N/A | 0 |
| local-faults | localhost/adaptive/plain/cc=off/loss=deterministic/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 11.5707 | N/A | 0 |
| local-faults | localhost/fixed/bitmap/cc=off/loss=deterministic/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 11.3170 | N/A | 0 |
| local-faults | localhost/adaptive/bitmap/cc=off/loss=deterministic/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 11.5740 | N/A | 0 |
| local-faults | localhost/adaptive/bitmap/cc=on/loss=deterministic/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 5.1913 | N/A | 0 |
| local-delay | localhost/fixed/plain/cc=off/loss=0/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.9783 | N/A | 0 |
| local-delay | localhost/adaptive/plain/cc=off/loss=0/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.9770 | N/A | 0 |
| local-delay | localhost/fixed/bitmap/cc=off/loss=0/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.9777 | N/A | 0 |
| local-delay | localhost/adaptive/bitmap/cc=off/loss=0/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.9780 | N/A | 0 |
| local-delay | localhost/adaptive/bitmap/cc=on/loss=0/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.1717 | N/A | 0 |
| local-faults | localhost/fixed/plain/cc=off/loss=deterministic/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.7093 | N/A | 0 |
| local-faults | localhost/adaptive/plain/cc=off/loss=deterministic/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.7103 | N/A | 0 |
| local-faults | localhost/fixed/bitmap/cc=off/loss=deterministic/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.7103 | N/A | 0 |
| local-faults | localhost/adaptive/bitmap/cc=off/loss=deterministic/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.7090 | N/A | 0 |
| local-faults | localhost/adaptive/bitmap/cc=on/loss=deterministic/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.1140 | N/A | 0 |
