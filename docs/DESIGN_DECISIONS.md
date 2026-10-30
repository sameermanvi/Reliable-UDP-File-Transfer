# Design decisions and comparison notes

## What we improved in this repository

| Previous behavior | Current implementation | Why it matters in the demo |
| --- | --- | --- |
| Raw UDP file chunks | Versioned header with type, length, transfer ID, sequence and CRC | Receiver knows what each datagram represents |
| No ACKs or retries | Individual ACKs and bounded per-packet retries | Missing DATA or ACKs trigger recovery |
| No ordering/deduplication | Selective Repeat and a 32-slot receive buffer | Reordered packets become correctly ordered file bytes |
| Receive silence meant success | Explicit FIN and FIN_ACK | A stalled transfer is not mistaken for a complete file |
| No file-integrity validation | Advertised size and whole-file CRC, independent SHA-256 in tests | Truncation, unexpected bytes, and accidental corruption are checked |
| Output opened/truncated immediately | Temporary file, verified close, then rename | Failed transfers preserve the previous destination |
| Empty build/test files | Warning-enabled Makefile and deterministic fault tests | Local fault tests complement the Mininet experiments |
| Per-chunk console output only | Transfer time, goodput and retransmission counters | Experiments retain counters and measured results |

These are improvements over this repository's original raw UDP implementation.
They are not claims that this project invented reliable UDP or Selective Repeat.

## Reference review and choices

The linked repositories were reviewed as conceptual references. No source code
was copied or vendored. They illustrate alternatives; the table describes our
chosen design rather than asserting that every reference lacks a feature.

| Reference | Idea considered | Our choice and explanation |
| --- | --- | --- |
| [EeshaArif: Reliable File Transfer](https://github.com/EeshaArif/Reliable-File-Transfer-UDP-Without-Timeout) | C, sequence ordering, Selective Repeat, window-and-wait without timeout | Keep C and explicit sequences; use timeout-driven recovery so silence cannot wait forever |
| [andrewzk: Reliable-UDP](https://github.com/andrewzk/Reliable-UDP) | C reliability layer with sessions and callbacks | Share wire/I/O helpers, but keep one upload and direct state transitions for a smaller explanation surface |
| [ffahleraz: sliding-window-protocol](https://github.com/ffahleraz/sliding-window-protocol) | Sliding window, checksums, separate sender/ACK threads | Use one poll-based loop with per-slot timers; no mutex or thread coordination required |
| [nimbid: UDP Based File Transfer](https://github.com/nimbid/Reliable-UDP-Based-File-Transfer) | FTP/TFTP-inspired transfer service | Keep a single upload command and local output path rather than GET/PUT, directory commands, and authentication |
| [JordanMontgomery: go-back-n](https://github.com/JordanMontgomery/go-back-n) | C Go-Back-N ARQ | Choose Selective Repeat so buffered suffix packets do not need retransmission when one earlier packet is lost |
| [dileepramesh: Reliable-UDP](https://github.com/dileepramesh/Reliable-UDP) | TCP-like reliability over UDP | Build explicit ACK/retry semantics without claiming to reproduce TCP's full feature set |
| [RikilG: Reliable-UDP](https://github.com/RikilG/Reliable-UDP) | Reliable UDP transfer and network impairment testing | Use repeatable application-level faults alongside Linux netem experiments |
| [8tiqa: go-back-n-udp](https://github.com/8tiqa/go-back-n-udp) | Python Go-Back-N alternative | Useful baseline for explaining why individual ACKs and buffering change retransmission cost |
| [pskalip: Selective Repeat](https://github.com/pskalip/Reliable-UDP-With-Selective-Repeat) | Selective Repeat algorithm | Track ACK state and timeout independently for every outstanding DATA packet |
| [deadsmash07: Networks-A4](https://github.com/deadsmash07/Networks-A4) | Loss/delay experiment sweeps and separate congestion-control studies | Compare normal, loss and failed-link trials; adaptive congestion control remains future work |
| [gibsjose: UDPFileTransfer](https://github.com/gibsjose/UDPFileTransfer) | Sliding-window walkthrough and Mininet testing notes | Explain missing-middle-packet recovery and reproduce link failure in Mininet |
| [haseeb-saeed: go-back-N](https://github.com/haseeb-saeed/go-back-N) | Reliable UDP with Go-Back-N | Keep the comparison as an algorithm explanation; no performance superiority is assumed |
| [rachhshruti: reliable-file-transfer-udp](https://github.com/rachhshruti/reliable-file-transfer-udp) | Broader UDP transfer design | Keep this phase focused on correctness; document flow/congestion control as future work |

## How to compare with FTP, FTPS, and TCP

FTP is an application protocol that normally uses TCP and separate control/data
connections, as specified in [RFC 959](https://www.rfc-editor.org/rfc/rfc959).
It already benefits from TCP's reliable ordered delivery. FTPS adds TLS to FTP;
SFTP is a different protocol. This project is a custom upload protocol, not a
compatible implementation of any of them.

| Comparison | Defensible statement | Limit |
| --- | --- | --- |
| Raw UDP | We add ordering, ACKs, retries, duplicate suppression and completion validation | More protocol work, memory and extra traffic |
| Stop-and-wait | Up to 32 chunks may be in flight rather than one | Gain depends on RTT, bandwidth, loss and processing cost |
| Go-Back-N | Only outstanding packets whose own ACK timers expire are retransmitted | Needs receiver buffering and individual ACK tracking |
| FTP/TCP | Reliability state and counters are visible in the application and easy to modify for experiments | No demonstrated speed advantage over TCP; TCP also recovers losses and many path changes |
| FTPS/SFTP | Our small C implementation makes transport mechanics easy to inspect in a lab | No encryption, authentication, mature service features, or production security equivalence |
| SDN comparison | Static and failover routing use the same transfer protocol and topology | Results apply to the recorded lab configuration; see VALIDATION.md |

A fixed window bounds memory; it is not adaptive congestion control. UDP
applications must consider congestion and fair sharing; see
[RFC 8085](https://www.rfc-editor.org/rfc/rfc8085). Our fixed 200 ms timer is easy
to demonstrate, but it can retransmit unnecessarily on long-RTT paths. This phase
is intended for isolated lab networks, not general Internet deployment.
CRC-32 detects accidental errors; it is not a secure hash or authentication.
The test harness independently checks SHA-256, but SHA-256 is not transmitted by
the C protocol. Do not present the protocol as cryptographically verified.

## Short viva explanation

"UDP gives us datagrams without delivery or ordering guarantees. We add a
sequence number and checksum to each chunk, keep up to 32 chunks in flight, and
ACK each one. The receiver buffers out-of-order chunks; the sender retries only
unacknowledged chunks after their timers expire. START declares the file size
and checksum, and FIN completes the transfer only after the receiver verifies
both. We test DATA loss, ACK loss, corruption, duplication and reordering, then
run active transfers while the SDN controller changes the network path. Our goal is an explainable and measurable
reliability layer, not a claim that UDP automatically beats TCP."

## Evidence required before claiming better performance

Use the same input, topology, bandwidth, RTT, queue configuration and loss pattern
for every baseline. Compare against a maintained TCP transfer tool and, if needed,
separate stop-and-wait / Go-Back-N implementations. Repeat each case and report
variation, verified output hashes, elapsed time, goodput, retransmissions, and
failed runs. Include metadata/file I/O consistently in end-to-end benchmarks.
Do not interpret the current localhost correctness tests as FTP benchmarks.

For the SDN experiment, record controller switch time, the last acknowledged
progress before the interruption, first new progress after switching, and final
integrity. Outages exceeding the retry or inactivity budgets are expected to
fail. Measured outcomes are linked from VALIDATION.md; differences between routing
policies must not be presented as a speed advantage over TCP.
