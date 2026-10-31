# Experiment summary

All rows are retained. Rates include failures; numeric performance summaries use successful transfers only. N/A is not zero. Multiple flows in one trial share a network and are not independent trials.

| Scenario | Mode | Trials | Successful flows | Expected outcomes | Mean goodput (Mb/s) | Mean recovery (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| local-delay | localhost/fixed/plain/cc=off/loss=0/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 15.5760 | N/A |
| local-delay | localhost/adaptive/plain/cc=off/loss=0/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 14.8413 | N/A |
| local-delay | localhost/fixed/bitmap/cc=off/loss=0/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 15.0053 | N/A |
| local-delay | localhost/adaptive/bitmap/cc=off/loss=0/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 15.1267 | N/A |
| local-delay | localhost/adaptive/bitmap/cc=on/loss=0/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 6.7810 | N/A |
| local-faults | localhost/fixed/plain/cc=off/loss=deterministic/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 11.4857 | N/A |
| local-faults | localhost/adaptive/plain/cc=off/loss=deterministic/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 11.5740 | N/A |
| local-faults | localhost/fixed/bitmap/cc=off/loss=deterministic/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 11.3203 | N/A |
| local-faults | localhost/adaptive/bitmap/cc=off/loss=deterministic/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 11.5740 | N/A |
| local-faults | localhost/adaptive/bitmap/cc=on/loss=deterministic/fail=0/flap=0/delay=5ms | 3 | 3/3 | 3/3 | 5.1577 | N/A |
| local-delay | localhost/fixed/plain/cc=off/loss=0/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.9793 | N/A |
| local-delay | localhost/adaptive/plain/cc=off/loss=0/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.9807 | N/A |
| local-delay | localhost/fixed/bitmap/cc=off/loss=0/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.9820 | N/A |
| local-delay | localhost/adaptive/bitmap/cc=off/loss=0/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.9780 | N/A |
| local-delay | localhost/adaptive/bitmap/cc=on/loss=0/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.1713 | N/A |
| local-faults | localhost/fixed/plain/cc=off/loss=deterministic/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.7100 | N/A |
| local-faults | localhost/adaptive/plain/cc=off/loss=deterministic/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.7090 | N/A |
| local-faults | localhost/fixed/bitmap/cc=off/loss=deterministic/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.7113 | N/A |
| local-faults | localhost/adaptive/bitmap/cc=off/loss=deterministic/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.7110 | N/A |
| local-faults | localhost/adaptive/bitmap/cc=on/loss=deterministic/fail=0/flap=0/delay=130ms | 3 | 3/3 | 3/3 | 0.1100 | N/A |
