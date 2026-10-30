# Viva reference

Retained from the newer guide and updated for the restored protocol.

## Viva questions

| Question | Answer |
| --- | --- |
| Why UDP rather than TCP? | UDP lets us demonstrate ACKs, windows, retransmission and ordering at application level. |
| Why Selective Repeat instead of Stop-and-Wait or Go-Back-N? | Stop-and-Wait waits after each packet. Go-Back-N resends the missing packet and later packets. Selective Repeat keeps a window in flight and retries only packets still missing. |
| What if a middle packet is lost? | Later packets are buffered and ACKed. The missing packet times out and is retried; once it arrives, the receiver writes the consecutive buffered packets. |
| How does the controller know a link failed and reroute? | An OpenFlow port-status event identifies the failed port. The controller selects the available diamond branch and replaces forward and reverse flow rules, then checks barrier replies. |
| Why 32 packets and 200 ms? | They are fixed, understandable lab settings; they are not adaptive or universally optimal. |
| What if an ACK is lost? | The sender retries DATA; the receiver ACKs the duplicate without writing it again. |
| What does SDN add? | Retries cannot repair a broken route; the controller installs an alternate route. |
| How do you prove correctness? | Check packet/file CRC and independently compare source/output SHA-256 or bytes. |
| Why keep a static baseline? | It shows the effect of rerouting under the same outage and application settings. |
| Is Docker the network controller? | No. It supplies the Linux environment; OS-Ken controls the OpenFlow switches. |

