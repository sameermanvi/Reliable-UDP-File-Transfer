# Architecture

The file application uses pure C and POSIX UDP sockets. Python only builds the
Mininet lab, runs the SDN controller and checks results.

```text
client (h1) -- s1 -- s2 -- s4 -- server (h2)
                \-- s3 --/
                  alternate path

Application: START -> START_ACK -> DATA/ACK -> FIN -> FIN_ACK
Network:     OpenFlow port-down event -> controller -> new switch flows
```

The initial path is s1-s2-s4. The controller selects s1-s3-s4 when the
primary branch fails and updates forwarding in both directions. The endpoints
keep the same UDP sockets and IP addresses. A static mode keeps the initial
route for comparison. The application never calls the controller.

## Selective Repeat

DATA payloads contain at most 1024 bytes. The sender keeps a fixed window of
16 packets and one ACK flag and timer per slot. Each packet is retried after
250 ms, with at most 30 retries after the first send. ACKs identify individual
sequence numbers. The receiver stores packets within its current window and
writes only consecutive packets from its base. A duplicate is acknowledged
without writing its bytes again.

```text
sender:   [ acknowledged ][ base ... base+15 ][ not sent ]
receiver: [ written      ][ buffered/missing ][ outside window ]
                                      ACK -> mark one sender slot
                          timeout -> resend only that unacknowledged slot
```

START announces the file size and whole-file CRC-32. FIN is accepted only after
all expected bytes arrive and the file CRC matches. The receiver stays alive
for 8 seconds after completion to answer duplicate FINs. A receiver waiting
for traffic fails after 10 seconds of inactivity. Each process serves one
transfer; separate ports and processes support independent simultaneous flows.

## Wire format

All multi-byte fields use network byte order. Every datagram starts with this
16-byte header; CRC-32 covers the header with its CRC field zeroed and the payload.

| Byte offset | Field | Size |
| --- | --- | --- |
| 0 | Magic `0x52554450` | 4 |
| 4 | Version `1` | 1 |
| 5 | Type | 1 |
| 6 | Payload length | 2 |
| 8 | Sequence number | 4 |
| 12 | Packet CRC-32 | 4 |

Types are START=1, START_ACK=2, DATA=3, ACK=4, FIN=5, FIN_ACK=6 and
ERROR=7. START carries an 8-byte size and 4-byte file CRC. There is no transfer
ID. Start a fresh receiver for every upload.

## Files and measurements

The receiver creates the requested output directly and refuses an existing
output path. A failed transfer removes the partial output it created; there is
no temporary file or atomic rename. Keep the input unchanged while sending.

The client prints bytes, elapsed seconds, retransmissions and file CRC. Goodput
is payload bytes times eight divided by elapsed seconds. An external SHA-256
comparison checks the output independently. A recovery interval measured from
link-down to renewed ACK progress includes detection, rule installation and
retransmission; it is not just controller execution time. See VALIDATION.md for
actual executed checks, and generated result files for any measured values.
