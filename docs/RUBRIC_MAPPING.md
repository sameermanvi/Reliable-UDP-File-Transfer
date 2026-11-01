# Official 40-mark rubric: implementation and evidence map

This is an evidence checklist, not a predicted score. The final Linux Docker/userspace OVS evaluation is complete;
see VALIDATION.md for runtime and evidence boundaries.

| Bucket | Marks | Final implementation | Artifact / assessment action |
| --- | ---: | --- | --- |
| D1 Problem Understanding & Architecture | 2 | Responsibility split, packet/state diagram, fixed diamond ports | ARCHITECTURE.md and VIVA.md |
| D1 TCP/UDP Socket Implementation | 4 | C/POSIX UDP, SR, CRC, explicit completion, validated SACK | src/client.c, server.c, utils.c; final native tests.log |
| D1 Mininet + SDN Implementation | 4 | OpenFlow 1.3 diamond, ARP/IPv4 forwarding, controller barriers | Final matrix per-trial network-initial/final.txt |
| D1 Socket–SDN Integration | 3 | Same transfer across route change; shared monotonic clock | Final per-trial timelines, recovery events and hash-bearing metrics |
| D1 Initial Testing & Demo | 2 | make test; one-command live preflight | 48 passing tests; completed Linux failover trials; rehearse demo.py |
| D2 Complete Application Functionality | 4 | Binary/empty/boundary files, selective retries, atomic replacement | final local tests.log and 60/60 hash-bearing benchmark rows |
| D2 Dynamic SDN Functionality | 6 | Static vs failover; hard failure; bidirectional probes; soft-score hysteresis | 48 upper→lower and 3 lower→upper successes; 3 soft-degradation successes |
| D2 Challenging Scenario / Robustness | 4 | Loss, duplication, corruption, reordering, bounded timeouts, flaps | Local fault tests and 6 successful Linux loss/reordering/flap trials |
| D2 Performance Evaluation & Comparison | 5 | Three-repeat routing/RTO/ACK/loss/fault-time matrix; hashes; all failures retained | 60 local transfers and 180 Linux expectations across three repeats |
| D2 Documentation, Final Demo & Viva | 6 | README, report, decisions, validation, short answers and one-page demo | Docs match current code; live execution must still be rehearsed on assessment host |

## Required hand-in evidence

The retained `results/rubric-final/` bundle is the completed evaluation.
Use a fresh output directory for any rerun.
Keep that entire directory: commands, environment/source fingerprint, complete
unit log, every trial row and hash, endpoint/controller/probe/progress logs,
interventions/outages, flow/queue dumps and plots. Static permanent-link failure
is an expected failed transfer, never a successful upload. Missing recovery is
censored/N/A. See DEMO.md for the reliable short live sequence and contrast.
