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

Mininet and the SDN controller are deferred. Their existing files are unchanged.

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
