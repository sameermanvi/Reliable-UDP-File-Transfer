# Official 40-mark rubric: implementation and evidence map

This is an evidence checklist, not a predicted score. Final Linux integration is
pending; local tests and historical logs cannot fill that gap by assertion.

| Bucket | Marks | Final implementation | Artifact / assessment action |
| --- | ---: | --- | --- |
| D1 Problem Understanding & Architecture | 2 | Responsibility split, packet/state diagram, fixed diamond ports | ARCHITECTURE.md and VIVA.md |
| D1 TCP/UDP Socket Implementation | 4 | C/POSIX UDP, SR, CRC, explicit completion, validated SACK | src/client.c, server.c, utils.c; final native tests.log |
| D1 Mininet + SDN Implementation | 4 | OpenFlow 1.3 diamond, ARP/IPv4 forwarding, controller barriers | Historical network dumps; final Linux matrix network-initial/final.txt pending |
| D1 Socket–SDN Integration | 3 | Same transfer across route change; shared monotonic clock | Historical joined timeline available; final per-trial timeline/recovery/hash pending |
| D1 Initial Testing & Demo | 2 | make test; one-command live preflight | 48 passing local tests; scripts/demo.py on Linux pending |
| D2 Complete Application Functionality | 4 | Binary/empty/boundary files, selective retries, atomic replacement | final local tests.log and 60/60 hash-bearing benchmark rows |
| D2 Dynamic SDN Functionality | 6 | Static vs failover; hard failure; bidirectional probes; soft-score hysteresis | Probe/handler/policy tests pass; final Linux hard/soft reroute evidence pending |
| D2 Challenging Scenario / Robustness | 4 | Loss, duplication, corruption, reordering, bounded timeouts, flaps | Local tests pass; combined netem/flap scenario on Linux pending |
| D2 Performance Evaluation & Comparison | 5 | Three-repeat routing/RTO/ACK/loss/fault-time matrix; hashes; all failures retained | Final local timer/ACK ablations available; complete Linux matrix pending |
| D2 Documentation, Final Demo & Viva | 6 | README, report, decisions, validation, short answers and one-page demo | Docs match current code; live execution must still be rehearsed on assessment host |

## Required hand-in evidence

Run `sudo .venv/bin/python scripts/evaluate.py --output results/rubric-final`.
Keep that entire directory: commands, environment/source fingerprint, complete
unit log, every trial row and hash, endpoint/controller/probe/progress logs,
interventions/outages, flow/queue dumps and plots. Static permanent-link failure
is an expected failed transfer, never a successful upload. Missing recovery is
censored/N/A. See DEMO.md for the reliable short live sequence and contrast.
