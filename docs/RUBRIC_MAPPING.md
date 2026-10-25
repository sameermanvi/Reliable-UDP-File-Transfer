# Implementation checklist and rubric mapping

This Markdown checklist tracks the implemented core; the original project guide
PDF is retained unchanged. SDN/Mininet experiments are deferred.

| Status | Requirement | Evidence |
| --- | --- | --- |
| Implemented | Basic binary UDP client/server | `src/client.c`, `src/server.c` |
| Implemented | Sequence numbers and stop-and-wait control | START/FIN exchanges in `client.c`; DATA uses Selective Repeat |
| Implemented | Selective Repeat sliding window | 32-slot sender/receiver rings, individual ACKs and per-packet timers |
| Implemented | Packet checksum and duplicate detection | CRC-32 in `utils.c`; receiver duplicate ACK handling |
| Implemented | Explicit completion | FIN/FIN_ACK and bounded duplicate-FIN linger |
| Implemented | File size and checksum | START metadata and receiver whole-file CRC comparison |
| Implemented in tests | Independent cryptographic file hash | Python SHA-256 checks of transferred files; not a protocol feature |
| Implemented | Makefile and clean compile instructions | `src/Makefile`, README |
| Implemented | Localhost correctness and impairment tests | `tests/test_protocol.py`, `scripts/test_transfer.sh` |
| Implemented | Basic performance counters | Client elapsed time, goodput, DATA/control retries; receiver duplicate/reorder counts |
| Pending | Adaptive timer / congestion control | Fixed window and timer only |
| Deferred | Mininet topology with two alternate paths | Existing placeholders unchanged |
| Deferred | Ryu initial flows and path switching | No controller changes in this phase |
| Deferred | Transfer survives a real path change | Needs integrated Mininet/Ryu experiments |
| Deferred | Performance comparisons and recovery measurements | Counters available; no comparative benchmark claims |
| Pending | Final experimental findings and demo readiness | Core is ready for localhost validation; network experiments remain |
