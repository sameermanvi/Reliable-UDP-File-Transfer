# Reliable UDP File Transfer with SDN

A student networking project: a pure C UDP uploader adds Selective Repeat
reliability, and a real OpenFlow controller reroutes its packets when a Mininet
link fails. This is a custom file-transfer protocol, not standard FTP.

## Localhost

On Linux or macOS, install a C11 compiler, Make and Python 3. From the repository root:

```sh
make
printf 'hello UDP\n' > /tmp/rudp-input.txt
./server 9000 /tmp/rudp-output.txt
```

In a second terminal, within 10 seconds:

```sh
./client 127.0.0.1 9000 /tmp/rudp-input.txt
cmp /tmp/rudp-input.txt /tmp/rudp-output.txt
```

Choose a fresh output filename each time: the server refuses existing files.
Each server accepts one upload and exits after an 8-second final-ACK wait.
Failed transfers remove the partial output they created. Use separate server
processes and UDP ports for concurrent transfers. Both programs return nonzero
on failure. Test the C application with:

```sh
make test
```

## How Selective Repeat works

1. START announces the file size and whole-file CRC-32.
2. The sender splits the input into payloads of at most 1024 bytes.
3. It keeps up to 16 DATA packets in flight, each with its own sequence number.
4. The receiver ACKs packets individually and buffers in-window reordered DATA.
5. Only contiguous DATA is written; duplicate packets are ACKed without rewriting.
6. Each unacknowledged packet is retried after 250 ms, up to 30 retries.
7. FIN/FIN_ACK completes the upload after the size and file CRC match.

Every packet also has a CRC-32. CRC detects accidental corruption; it does not
provide authentication. The [architecture](docs/ARCHITECTURE.md) describes the
16-byte header, windows and timers.

## Mininet and controller

Use an Ubuntu 22.04 Linux machine or VM with root access. Mininet cannot run
natively on macOS. Install the lab and controller dependencies:

```sh
sudo apt-get update
sudo apt-get install -y build-essential python3-venv python3-pip mininet openvswitch-switch iproute2 iputils-ping net-tools procps ethtool
sudo python3 -m venv --system-site-packages /opt/sdn
sudo /opt/sdn/bin/pip install -r requirements-sdn.txt
sudo service openvswitch-switch start
make
sudo /opt/sdn/bin/python scripts/demo.py --datapath kernel
```

The runner starts the controller and Mininet for each trial. The diamond has
h1-s1-s2-s4-h2 as its primary path and s1-s3-s4 as its alternate branch. OS-Ken,
a maintained Ryu fork, runs the Ryu-style OpenFlow 1.3 controller. It receives
port-status events, chooses the available branch and installs rules in both
directions. OpenFlow barriers confirm rule processing. The endpoints continue
using the same sockets; no application-side route change is required.

For an interactive inspection, start the controller in one terminal and the
network in another:

```sh
sh scripts/start_controller.sh
sudo sh scripts/start_topology.sh --datapath kernel
```

At the Mininet prompt:

```text
pingall
sh ovs-ofctl -O OpenFlow13 dump-flows s1
link s1 s2 down
sh ovs-ofctl -O OpenFlow13 dump-flows s1
link s1 s2 up
exit
```

## Docker demo and comparison

Docker gives every teammate the same Ubuntu userspace, compiler, Mininet and
pinned controller dependencies, making the commands reproducible across host
systems. It is an environment tool; it does not implement UDP reliability or
SDN rerouting. Install Docker Engine or Docker Desktop with Compose, then run
from the repository root:

```sh
docker compose run --build --rm demo
```

For a shorter run after the image is built:

```sh
docker compose run --rm demo python scripts/demo.py --repetitions 1 --mib 1
```

The privileged container needs network namespaces and virtual interfaces.
Its userspace OVS datapath avoids requiring an OVS kernel module in Docker's
Linux VM. Run it only on a machine where you can grant those privileges.

The default demo uses 2 MiB inputs and three repetitions. It compares normal
traffic, bidirectional netem impairments (8 ms delay, 2 ms jitter, 2% loss, 1%
duplication, 20% reordering with 50% correlation), and the same one-second
primary-link outage under static and dynamic routing. Static routing waits for
the original link to return; dynamic routing can use the alternate branch.

Results go to `results/demo-TIMESTAMP/`. `metrics.csv` records scenario, mode,
bytes, retransmissions, seconds, recovery interval, route interval and SHA-256.
Each trial retains endpoint logs, controller logs/events and progress timestamps.
Successful output hashes are checked against the input. Recovery is measured
from the fault to renewed contiguous ACK progress after route confirmation
(dynamic) or link restoration (static). Route time ends at the OpenFlow barrier.
These definitions and the VM environment limit interpretation of the numbers.
See [VALIDATION](docs/VALIDATION.md) for checks actually executed; commands and
expected behavior alone are not measured evidence.

## Viva answer

We use UDP so that we can implement and explain reliability ourselves in C.
Selective Repeat sends a window of 16 packets, ACKs each sequence number, buffers
reordering and retries only missing packets after 250 ms. CRC-32 checks packets
and the completed file. In Mininet, the controller detects a failed primary
link and changes OpenFlow rules to use the alternate path while the same
transfer continues. We compare this with static routing using file integrity,
transfer time, retransmissions and recovery time. Docker packages the Linux lab
and pinned dependencies so teammates can reproduce the demonstration. For the
examiner: we use Docker for the same Linux tools and dependency versions on every
teammate's machine; the C application and SDN controller still implement the project.

## Viva questions

| Question | Answer |
| --- | --- |
| Why UDP rather than TCP? | UDP lets us demonstrate ACKs, windows, retransmission and ordering at application level. |
| Why Selective Repeat instead of Stop-and-Wait or Go-Back-N? | Stop-and-Wait waits after each packet. Go-Back-N resends the missing packet and later packets. Selective Repeat keeps a window in flight and retries only packets still missing. |
| What if a middle packet is lost? | Later packets are buffered and ACKed. The missing packet times out and is retried; once it arrives, the receiver writes the consecutive buffered packets. |
| How does the controller know a link failed and reroute? | An OpenFlow port-status event identifies the failed port. The controller selects the available diamond branch and replaces forward and reverse flow rules, then checks barrier replies. |
| Why 16 packets and 250 ms? | They are fixed, understandable lab settings; they are not adaptive or universally optimal. |
| What if an ACK is lost? | The sender retries DATA; the receiver ACKs the duplicate without writing it again. |
| What does SDN add? | Retries cannot repair a broken route; the controller installs an alternate route. |
| How do you prove correctness? | Check packet/file CRC and independently compare source/output SHA-256 or bytes. |
| Why keep a static baseline? | It shows the effect of rerouting under the same outage and application settings. |
| Is Docker the network controller? | No. It supplies the Linux environment; OS-Ken controls the OpenFlow switches. |

## Limits

This is one upload per process, with no resume, authentication, encryption,
congestion control, adaptive timeout, transfer ID or atomic rename. Fresh
receivers reduce confusion from stale datagrams; this is not a production
session protocol. Fixed retry and inactivity limits can terminate a transfer
under long outages. The controller knows this diamond's ports; it does not
implement general topology discovery or congestion-aware routing. Tests on
localhost do not establish Mininet or Docker behavior.

The [rubric mapping](docs/RUBRIC_MAPPING.md) uses the supplied assessment weights.
The [original team guide](docs/Project_Guide_and_Checklist.pdf) is unchanged.
[MIT license](LICENSE).
