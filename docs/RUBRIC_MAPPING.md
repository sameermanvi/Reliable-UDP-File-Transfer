# Assignment checklist and rubric mapping

The assigned problem is **Reliable File Transfer over UDP**: application-level
reliability plus SDN detection of path problems and rerouting during failures.
The original [project guide](Project_Guide_and_Checklist.pdf) is retained
unchanged. This checklist identifies the implementation and the evidence needed
for assessment; it is not a prediction of marks.

## Project requirements

| Requirement | Implementation | Evidence to show |
| --- | --- | --- |
| UDP file transfer | C client and server using POSIX datagram sockets | Binary upload on the Mininet hosts and matching final hash |
| Sequence numbering | 32-bit DATA chunk indices and a transfer ID | Packet format, sender window and receiver ordering |
| Acknowledgments | Individual DATA ACKs, START_ACK and FIN_ACK | Normal and lost-ACK test cases |
| Timeouts and retransmission | Per-packet 200 ms timer with at most 30 retries | Retry counters, packet-loss run and bounded failure |
| Missing/duplicate handling | Selective Repeat window and duplicate ACK handling | Out-of-order buffering, selective retry and no duplicated output bytes |
| File integrity | Declared size and whole-file CRC-32; external SHA-256 check | Source/output hashes and rejection of corrupt or incomplete transfers |
| SDN path-problem detection | OpenFlow port status events in the controller | Link-down event with switch, port and timestamp |
| Rerouting during failures | Alternate branch selection and bidirectional flow updates | Controller route event, flow-table change and new ACK progress |

## D1: 15 marks

| Component | Marks | Repository material | Demonstration/evidence |
| --- | --- | --- | --- |
| Problem understanding and architecture | 2 | `ARCHITECTURE.md`, packet layout, diamond topology | Explain which failures UDP reliability handles and which require a new network path |
| TCP/UDP socket implementation | 4 | `src/client.c`, `src/server.c`, `src/utils.c` | Correct binary transfer, ordering, ACKs, retries, error handling and clean completion |
| Mininet + SDN implementation | 4 | `mininet/topology.py`, `controller/failover.py` | Four connected OpenFlow 1.3 switches, endpoint connectivity and installed rules |
| Socket–SDN integration | 3 | C endpoints launched on Mininet hosts by the experiment runner | Same active transfer continues after the controller changes the route |
| Initial testing and demo | 2 | Protocol/controller tests and a normal Mininet trial | Reproduce a successful end-to-end transfer and verify its output |

## D2: 25 marks

| Component | Marks | Repository material | Demonstration/evidence |
| --- | --- | --- | --- |
| Complete application functionality | 4 | Reliable upload, integrity validation, explicit completion, atomic output replacement | Files of different sizes; independent concurrent transfers on separate receiver ports |
| Dynamic SDN functionality | 6 | Controller `failover` policy and event log | Fail the primary path during a transfer and inspect alternate-path rules |
| Challenging scenario / robustness | 4 | Deterministic protocol fault tests and Mininet loss/link-failure scenarios | Lost DATA/ACKs, duplicates, reordering, corruption, link failure and safe timeout failure |
| Performance evaluation and comparison | 5 | Experiment CSV/JSON, raw logs and generated plots | Repeated static/failover trials under matching conditions; integrity, goodput, retries and recovery measurements |
| Documentation, final demo and viva | 6 | README, architecture, demo, report, design decisions and validation record | Fresh-machine reproduction, measured findings, limitations and individual explanations |

## What counts as completion

Implementation files and unit tests establish code availability and local
behavior. Integrated Mininet execution establishes network behavior. The
comparison requires actual recorded trials; counters alone are not a benchmark.
See `VALIDATION.md` for executed checks and `REPORT.md` for presenting results.

For the final submission, retain the source revision, environment information,
topology parameters, controller and endpoint logs, all trial rows, and generated
figures. Include failed trials instead of selecting only successful runs. A
static route failing after its only selected path is removed is the expected
baseline outcome, while an unexpected failover failure needs explanation.

Adaptive congestion control, encryption and compatibility with standard FTP are
outside the assigned requirement list. They must not be presented as completed
features. Each receiver process handles one upload; concurrent experiment flows
use separate processes and ports.
