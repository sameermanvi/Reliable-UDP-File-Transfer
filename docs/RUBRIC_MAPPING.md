# Rubric mapping

Source: the supplied `SDN-Socket Programming-Guidelines_Rubrics.pdf`,
Evaluation Criteria and Detailed Rubric tables. The original team guide is
[retained unchanged](Project_Guide_and_Checklist.pdf). These are evidence targets,
not awarded marks. Test results are recorded separately in [VALIDATION.md](VALIDATION.md).

## D1: 15 marks

| Official component | Marks | Implementation and evidence to present |
| --- | --- | --- |
| Problem Understanding & Architecture | 2 | README and ARCHITECTURE: UDP reliability, components, topology and expected failure behavior |
| TCP/UDP Socket Implementation | 4 | C client/server: binary transfer, ACKs, sequence numbers, timeouts, duplicate handling, errors and completion |
| Mininet + SDN Implementation | 4 | Diamond topology, working controller, connectivity and OpenFlow tables |
| Socket–SDN Integration | 3 | C endpoints in Mininet; same transfer survives primary-link failure through new controller-installed flows |
| Initial Testing & Demo | 2 | Reproducible normal transfer and independent output comparison |

## D2: 25 marks

| Official component | Marks | Implementation and evidence to present |
| --- | --- | --- |
| Complete Application Functionality | 4 | Successful normal uploads, file integrity and independent flows on separate server ports |
| Dynamic SDN Functionality | 6 | Port-status detection, alternate-route decision, bidirectional flow replacement and continued transfer |
| Challenging Scenario / Robustness | 4 | Packet loss or mid-transfer link failure; correct retry behavior and bounded failure |
| Performance Evaluation & Comparison | 5 | Actual normal/loss/failure measurements; static routing versus dynamic routing under matching conditions |
| Documentation, Final Demo & Viva | 6 | Setup, source, topology, configuration, tests, recorded results, limitations and individual explanations |

## Submission evidence

The official mandatory requirements include low-level sockets, multiple nodes
or clients wherever applicable, deployment in Mininet, interaction with the
SDN-controlled network, and reproduction instructions in the GitHub repository.
Here concurrency means separate client/server processes and ports, not a shared
multi-client server. Demonstrate two flows if using that claim.

For the comparison, save source revision, environment details, topology settings,
source/output hashes, endpoint logs, controller events and flow tables. Record
failed trials as well as successful ones. A static transfer may fail when its
only selected path is removed; dynamic routing should recover if the alternate
path stays available and the retry budget is sufficient. The existence of code
or an expected outcome does not establish that a test ran or that a rubric item
has been satisfied.
