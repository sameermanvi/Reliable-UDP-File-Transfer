# Architecture

## Responsibility split

The C client/server provide Selective Repeat ARQ, integrity, bounded retries and
explicit completion. OS-Ken programs paths in a four-switch Mininet diamond.
A new route cannot repair an already missing datagram; application recovery cannot
repair a permanently broken route. The assessed integration is one active transfer
surviving the network change, proven by continued ACK progress and a final hash.

```text
                s2
              /    \
h1 -- s1 ----        ---- s4 -- h2
              \    /
                s3
```

| Switch | Port 1 | Port 2 | Port 3 |
| --- | --- | --- | --- |
| s1 | h1 | s2 | s3 |
| s2 | s1 | s4 | — |
| s3 | s1 | s4 | — |
| s4 | s2 | s3 | h2 |

`mininet/topology.py` fixes OpenFlow 1.3 ports. Both branches have transit rules;
host ingress chooses the same branch for forward/reverse IPv4 and ARP. There is
no broadcast flooding around the diamond. `controller/routing.py` separates policy
from OpenFlow message construction in `controller/failover.py`.

## Wire protocol: v1 and negotiated bitmap extension revision 1

All integers are network byte order. Never send native C struct memory.

| Offset | Bytes | Field |
| --- | --- | --- |
| 0 | 4 | Magic 0x52554450 (RUDP) |
| 4 | 1 | Header version 1; other versions rejected |
| 5 | 1 | Type |
| 6 | 2 | Payload length, 0–1024 |
| 8 | 8 | Random transfer ID |
| 16 | 4 | DATA sequence or control sequence |
| 20 | 4 | IEEE CRC-32 over header+payload with this field zeroed |
| 24 | variable | Payload |

| Type | Name | Sequence | Payload |
| --- | --- | --- | --- |
| 1 / 2 | START / START_ACK | 0 | file size u64 + whole-file CRC u32 / empty |
| 3 | DATA | chunk index | 1–1024 file bytes |
| 4 | ACK | echoed DATA index | empty |
| 5 / 6 | FIN / FIN_ACK | total chunk count | empty |
| 7 | ERROR | 0 | diagnostic text |
| 8 / 9 | START_SACK / START_SACK_ACK | 0 | same 12-byte metadata / empty |
| 10 | SACK | echoed DATA index | receive base B (u32), occupancy M (u32) |

SACK acknowledges every sequence below B and buffered B+i when bit i of M is set
(LSB bit 0). The receiver drains contiguous bytes before reporting B, so bit 0
must be clear. The sender validates length, peer, transfer ID, echoed sequence,
base, all set bits and consistency between echo and coverage before mutating any
state. Bits cannot acknowledge unsent DATA. CRC protects accidental corruption;
neither CRC nor transfer ID authenticates a malicious endpoint.

The C state machine uses START, DATA, ACK, FIN and ERROR with flags for SACK
negotiation, bitmap presence and control replies. The codec maps legal combinations
to the v1 byte at offset 5. All 24 bytes are allocated, so adding a separate flag
octet would change existing packets.

Header v1 stays unchanged; explicit types 8/9 negotiate the single bitmap
extension revision. This is not an automatic downgrade protocol: an old server
requires `RUDP_SACK=0`. New servers accept both modes. Wrong START_ACK type cannot
complete negotiation. Unknown header versions are ignored.

## Sender and receiver state

The sender uses a ring of 32 slots, each holding DATA, ACK status, timestamp,
retry count, timeout and gap evidence. The receiver buffers at most 32 chunks and
writes only contiguous bytes. Empty files use START/FIN without DATA. Sequence
numbers never wrap; at most UINT32_MAX chunks are supported.

DATA RTO starts at 200 ms. A clean first RTT R sets SRTT=R and RTTVAR=R/2.
Later: RTTVAR = .75*RTTVAR + .25*abs(old SRTT−R), then
SRTT = .875*SRTT + .125*R. RTO = clamp(SRTT+4*RTTVAR, 50, 2000) ms.
Only an explicit echoed sequence with no retransmissions supplies a sample
(Karn's rule); cumulative/bitmap coverage alone does not. Slots snapshot RTO.
Each timeout doubles that slot's timer up to 2 s; the global timer backs off once
per outstanding-window epoch so a slow path can eventually supply clean samples.

Three distinct newly acknowledged later sequences trigger one fast retransmit of
a hole. Duplicated ACK datagrams do not count as fresh evidence. A lost fast retry
falls back to timeout recovery. This works in both plain and SACK modes, so ACK
format ablations hold fast retransmit constant. Reordering can cause a spurious
fast retry; no TCP fast recovery or reordering oracle is claimed.

CWND starts at four packets, increases by one per new ACK in slow start and by
1/cwnd in congestion avoidance, capped at 32. Timeout sets CWND to one; fast loss
halves it (minimum two). One reduction occurs per outstanding-window loss epoch.
Sending obeys both floor(cwnd) and the 32-slot sequence span; the latter is a
conservative bound behind a hole. This is basic loss response, not measured TCP
fairness. `RUDP_CC=0` restores the fixed 32-packet sending window.

Public switches: `RUDP_RTO=fixed|adaptive`, `RUDP_SACK=0|1`, `RUDP_CC=0|1`.
Defaults are adaptive/1/1. The old `RUDP_ADAPTIVE_RTO=0|1` alias remains accepted
when RUDP_RTO is absent. Invalid RUDP_RTO values fail immediately. Fixed mode uses
200 ms DATA timers without backoff. START/FIN keep fixed 200 ms timers to preserve
control retry and FIN linger semantics. DATA gets at most 30 retries. Receiver
inactivity is 10 s; sufficiently long outages fail safely even if sender retries
remain. Completion requires size+whole-file CRC agreement, successful close, and
atomic rename of a temporary file. This is not fsync-based crash durability.

## Dynamic SDN and real probes

Static mode retains the configured initial branch. Failover mode immediately
excludes branches with down ports or missing switches. Both paths down records
route_unavailable and blocks host ingress. A restored link does not itself force
failback. Initial branch defaults to upper; RUDP_INITIAL_PATH=lower permits the
reverse-direction recovery check.

`controller/probes.py` tracks independent Ethernet probes in both directions on
both branches, including the idle branch. Every 250 ms the controller sends a
60-byte experimental-EtherType 0x88b5 frame with a random session token and sequence
through the selected branch port. High-priority transit rules cross s2/s3; edge
rules punt the arriving frame to the controller and never to hosts. Validation
checks token, sequence, expected switch/port, deadline and duplicate status.
500 ms without a valid arrival counts as a lost probe.

Each direction smooths loss and observed elapsed latency with EWMA weight 1/4.
Branch score is the worse directional (loss EWMA + min(delay_ms,500)/1000).
Latency includes controller/OpenFlow overhead; it is not a pure link RTT or loss
probability. Both directions need four samples, each at most 2 s old. Health-only
moves require an improvement exceeding .02 and a 2 s route hold-down, and wait for
outstanding barriers. Hard port failures bypass that hold-down. Link changes clear
old branch health. Approximately 16 small frames/s probe both live branches.

## Socket–SDN observability and recovery definition

Client, receiver, harness and controller use CLOCK_MONOTONIC nanoseconds on the
same Linux kernel. Each endpoint has its own exclusively created JSONL log.
Controller decisions include score observations, cause, branch and generation;
route_ready follows all relevant OpenFlow barriers. Barriers prove rule processing,
not packet delivery or a globally atomic update.

Primary recovery metric: first strictly later **new contiguous ack_progress**
after alternate-path route_ready, minus the matching controller link_down time.
The prefix must exceed the greatest base already observed at route_ready. Also
report injection-to-progress, injection-to-route-ready and route-ready-to-progress.
Recovery is an observation after switching, not proof of the physical path of a
particular ACK. Final output SHA-256 establishes integrity independently.

No route or no later useful ACK is censored/N/A, never zero. Repeated-fault
attribution ends at the next intervention; a failure on the inactive branch is
labeled separately. The joined SVG and recovery JSON preserve all three timestamps.
See PROGRESS_LOG.md, DEMO.md and scripts/evaluate.py.
