# System Architecture

## Components

- `src/client.c`: reads metadata, establishes a transfer, sends a Selective Repeat
  window, retries missing ACKs, and confirms completion.
- `src/server.c`: accepts one transfer, validates and buffers DATA, writes ordered
  bytes, verifies integrity, and confirms FIN.
- `src/packet.h`: shared packet types and protocol limits.
- `src/utils.c` / `src/utils.h`: explicit serialization, CRC-32, port parsing,
  monotonic timers, random transfer IDs, and UDP I/O.
- `tests/test_protocol.py`: independent Python wire encoder and deterministic
  localhost impairment proxy; application reliability itself remains pure C.

The Linux lab adds three components around the same client and server:

- `mininet/topology.py`: two hosts and a four-switch diamond, with explicit
  OpenFlow 1.3 ports and configurable bandwidth, delay and loss.
- `controller/failover.py`: an OS-Ken controller that installs forwarding rules,
  watches link status and selects the upper or lower path.
- The experiment runner: launches the endpoints on Mininet hosts, introduces a
  fault during a transfer, checks the received SHA-256, and saves logs and metrics.

The application recovers missing datagrams through its existing ACK and retry
logic. The controller changes forwarding rules when a network link fails. Their
interaction is visible in the same live transfer; the application is not restarted
when the path changes.

## SDN topology and forwarding

```text
                  s2
                 /  \
 h1 --- s1 -----/    \----- s4 --- h2
          \                  /
           \------ s3 ------/

 upper path: h1 - s1 - s2 - s4 - h2
 lower path: h1 - s1 - s3 - s4 - h2
```

| Switch | Port 1 | Port 2 | Port 3 |
| --- | --- | --- | --- |
| s1 | h1 | s2 | s3 |
| s2 | s1 | s4 | - |
| s3 | s1 | s4 | - |
| s4 | s2 | s3 | h2 |

The topology fixes the port map so controller behavior is easy to inspect. Both
branches have transit rules; host ingress rules choose the active branch in both
directions. ARP and IPv4 follow the selected path without flooding around the
loop. Replies and DATA therefore use the same selected branch.

The controller has two modes. `static` retains the initial upper path even when
it fails, providing the comparison baseline. `failover` reacts to OpenFlow port
status events and selects an available alternate path. When a failed link comes
back, the controller retains the current working path to avoid an unnecessary
second interruption. If no route remains, it records `route_unavailable`.

Controller JSONL events contain a monotonic timestamp (`monotonic_ns`) and UTC
wall time. `link_down` and `link_up` identify the switch and port. A `route_ready`
event identifies the path, cause and generation after OpenFlow barriers confirm
that the switches processed the update. This is evidence of rule programming;
application progress and the final output hash establish that file delivery
actually resumed. These are separate measurements.

This controller targets the supplied diamond topology. It does not discover and
route through arbitrary networks or infer congestion from missing application
ACKs. Link failure detection uses SDN port status; packet loss alone is handled
by application retransmission.

## Packet format (version 1)

All multi-byte integers are unsigned and in network byte order. Native struct
memory is never sent, avoiding compiler padding and host-endianness dependence.

| Offset | Bytes | Field |
| --- | --- | --- |
| 0 | 4 | Magic `0x52554450` (`RUDP`) |
| 4 | 1 | Version = 1 |
| 5 | 1 | Packet type |
| 6 | 2 | Payload length, 0..1024 |
| 8 | 8 | Random transfer ID |
| 16 | 4 | Sequence number |
| 20 | 4 | Packet CRC-32 |
| 24 | 0..1024 | Payload |

CRC uses IEEE CRC-32 (polynomial `0xedb88320`, initial state and final XOR
`0xffffffff`). The packet checksum covers the complete header and payload with
the checksum field zeroed. Datagrams must match the advertised length exactly.
At most 1048 UDP payload bytes (1076 bytes including usual IPv4/UDP headers) fit
inside a typical 1500-byte MTU; smaller-MTU paths are not dynamically discovered.

| Value | Type | Sequence | Payload |
| --- | --- | --- | --- |
| 1 | START | 0 | 8-byte file size + 4-byte whole-file CRC-32 |
| 2 | START_ACK | 0 | Empty |
| 3 | DATA | Chunk index starting at 0 | 1..1024 file bytes |
| 4 | ACK | Individual acknowledged DATA index | Empty |
| 5 | FIN | Total DATA packet count | Empty |
| 6 | FIN_ACK | Total DATA packet count | Empty |
| 7 | ERROR | 0 | Diagnostic text, no terminating NUL required |

Packet count is `ceil(file_size / 1024)`; empty files have zero DATA packets.
The final DATA length is derived from the advertised size. At most `UINT32_MAX`
DATA packets are permitted (about 4 TiB); sequence numbers never wrap in a session.

## Protocol flow

```text
Client                                  Server
metadata scan (size and CRC)
START(size, CRC, transfer ID) ----------> validate; create temporary output
                            <---------- START_ACK
DATA(0)..DATA(31) ---------------------> buffer, write ordered prefix
                            <---------- ACK(each valid DATA)
retry only timed-out DATA -------------> re-ACK duplicates without rewriting
slide window as contiguous ACKs arrive
FIN(total packet count) ---------------> check count, size and whole-file CRC;
                                        close and rename temporary file
                            <---------- FIN_ACK
report success                          linger to re-ACK duplicate FINs; exit
```

START and FIN use stop-and-wait exchanges. A lost control ACK causes the same
control packet to be retried, rather than restarting or truncating the transfer.
Both endpoints require the expected peer IPv4/port and transfer ID after START.
The ID isolates stale sessions; it does not authenticate the sender.

## Selective Repeat example

The sender tracks each outstanding packet's ACK status, timestamp, and retry
count in a ring of 32 slots. The window covers indices `[base, base + 32)`.
If DATA 2 is lost while 3..31 arrive, the receiver keeps those later packets and
ACKs each one. The sender retransmits 2 after its timer expires. Receiving 2
allows the receiver to write the entire now-contiguous prefix. Once ACK 2 arrives,
the sender advances past all consecutive ACKed packets and fills the window.
It does not resend the entire suffix as Go-Back-N would.

The receiver stores at most 32 packet slots. DATA below its base is acknowledged
again, never written again. DATA beyond its receive window, malformed packets,
bad CRCs, wrong-length DATA, and unrelated sessions are ignored.

## Completion and failure semantics

A receive timeout is failure, never evidence that the file is finished. FIN is
accepted only after every expected chunk has been written and the total size and
whole-file CRC agree. The existing destination remains intact until the temporary
file closes successfully and is renamed. Atomic rename is not an fsync-based
power-loss durability guarantee.

The client makes at most 31 sends per packet: one original and 30 retries, spaced
200 ms apart. The server waits at most 10 seconds without valid in-window
DATA. Duplicate control packets and old DATA do not prolong this deadline.
After completion, a fixed 6.4-second linger covers the sender's FIN retry horizon;
duplicate FINs receive FIN_ACK without repeating the final write/rename.

ERROR is best effort. If ERROR is lost, client retry exhaustion still produces
failure. If every FIN_ACK is lost, the server can have a complete file while the
client reports failure: finite acknowledgements cannot guarantee that both sides
know the other's outcome. There is no restart/resume after process exit.

## Measurements

Client transfer time uses a monotonic clock from the first START through FIN_ACK;
it excludes the initial metadata scan and the server's linger. Goodput is file
payload bits divided by that time. `packets` counts original DATA chunks;
`data_sends` includes their retries, `retransmits` counts DATA retries only, and
`control_retransmits` counts START/FIN retries. Values rounded to 0.000 seconds
or sub-millisecond runs are not useful benchmark evidence.

The receiver counts valid repeated DATA as duplicates and first arrivals above
the current base as out-of-order. Its summary is printed before linger, so it
does not include late duplicates during that linger.

Set `RUDP_PROGRESS_LOG` to a new file path to collect client JSONL progress. The
client creates it exclusively, so an existing path is an error rather than a
truncated log. Each advance of the contiguous ACK prefix records
`event: "ack_progress"`, `monotonic_ns`, `base` (the next unacknowledged chunk)
and `bytes` (the acknowledged file prefix). Events are flushed as they occur.
An empty file has no DATA progress events. This optional logging changes no wire
messages and uses the same Linux monotonic clock as the experiment runner.

The runner correlates ACK progress with failure injection and controller events.
Barrier readiness measures controller rule installation; new contiguous ACK
progress measures resumption of useful delivery. Report those separately and
retain the raw timestamps so recovery definitions can be checked.
