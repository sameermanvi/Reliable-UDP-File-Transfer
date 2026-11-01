# Viva: short answers

| Question | Answer |
| --- | --- |
| What problem do you solve? | Deliver a correct binary file over unreliable UDP while SDN restores a broken network route during the same transfer. |
| Why UDP rather than TCP? | The lab assesses explicit socket reliability: ordering, ACKs, windows, timers and interaction with SDN. Production applications normally use a mature transport. |
| Why Selective Repeat over Go-Back-N? | The receiver buffers later chunks and the sender retries missing ones; Go-Back-N repeats the suffix after a loss. The cost is per-packet state and receive buffering. |
| Why a window of 32? | About 32 KiB of payload buffering, simple ring indexing, and one uint32 bitmap for the whole receive window. It is a lab cap, not an optimal bandwidth-delay product. |
| How does adaptive RTO work? | SRTT uses weight 1/8; variation uses 1/4 against the old SRTT. RTO is SRTT+4 variation, clamped to 50–2000 ms. Initial RTO is 200 ms. |
| What is Karn's rule? | Do not sample RTT from a retransmitted chunk: its ACK might refer to either send. Cumulative/bitmap coverage without a clean echoed sequence also supplies no RTT sample. |
| Why backoff as well as estimation? | If initial RTO is shorter than every RTT, all samples become ambiguous. Timeout backoff allows later clean samples. Slot timers double; the global timer backs off once per outstanding-window epoch. |
| What does the bitmap buy? | Later ACKs repeat which packets are buffered plus the written prefix. Losing an ACK need not force a DATA retry. It costs eight payload bytes. |
| How is SACK versioned? | Header version stays 1. Distinct START_SACK/START_SACK_ACK types negotiate bitmap extension revision 1. Old peers need RUDP_SACK=0; unsupported versions are rejected. |
| How do you validate a SACK? | Check peer, transfer ID, CRC/length, echoed sequence, base, all bitmap bits, and echo/coverage consistency before changing any slot. Nothing may acknowledge unsent DATA. |
| What triggers fast retransmit? | Three distinct newly ACKed later sequences reveal a gap. Copies of one ACK cannot trigger it. One fast retry per hole, then timeout fallback. |
| Is CWND the SR receive window? | No. Receive storage stays 32 slots. CWND separately limits sending, starts at four, grows and responds to loss, never exceeding 32. |
| How does the controller decide? | Hard-down branches are excluded immediately. Otherwise bidirectional probes score both live branches; fresh EWMA loss+latency scores, a .02 improvement threshold and a 2 s hold-down govern soft moves. |
| What do probes actually measure? | Successful arrival and elapsed controller-to-switch-to-controller time along a branch. Control-channel overhead is included; the score is not an exact end-to-end loss rate or RTT. |
| Why probe the idle path? | Application traffic cannot measure an unused backup. Separate Ethernet probe rules exercise both branches without moving the transfer. |
| What if both paths are degraded? | Prefer the better fresh score if the improvement exceeds hysteresis; retain a working route if evidence is missing or too close. Hard availability always wins. |
| What if both paths are down? | Record route_unavailable and drop host ingress. UDP retries are bounded; the receiver times out without replacing its destination. |
| What exactly is recovery latency? | Time from the matching controller link_down to the first strictly later new contiguous ACK prefix after alternate route_ready. Also report fault-injection-to-progress separately. |
| What if the transfer ends before recovery? | It is censored/N/A, not zero. The log must show both route readiness and later useful prefix advancement. |
| Does route_ready prove delivery? | No. It means OpenFlow barriers confirmed rule processing. Continued ACK progress and final SHA-256 supply application evidence. |
| What proves the integration? | One transfer ID spans the failure; the joined timeline shows link_down → route_ready → useful ACK progress, and the output hash matches. |
| What happens on a lost ACK? | Plain mode may retry the chunk. Bitmap mode can recover its coverage from a later report; old DATA duplicates are ACKed without rewriting. |
| Is CRC secure? | No. CRC catches accidental corruption. Transfer ID isolates sessions; neither authenticates peers. The harness uses independent SHA-256 for validation. |
| How do you know the file is complete? | FIN is accepted only after all advertised bytes are written and whole-file CRC agrees. Close succeeds, then the temporary file is renamed. Silence is failure, never success. |
| Why can adaptive RTO or CWND reduce speed? | A conservative timer can delay recovery, and slow start costs short-flow throughput. We report the measured tradeoff instead of assuming every mechanism makes every run faster. |
| What did you deliberately omit? | TCP byte-stream semantics, mature fairness/pacing, ECN, encryption, arbitrary topology discovery, resume and a frontend. They do not earn the targeted reliability/SDN evidence within this lab. |
| Which results validate the final SDN probes? | The final Linux bundle: 180/180 expectations, including 3/3 soft-degradation and 6/6 robustness trials. It used Ubuntu 22.04 Docker/userspace OVS; see VALIDATION.md. |

Live commands: DEMO.md. Artifact-backed numbers: KEY_RESULTS.md and REPORT.md.
