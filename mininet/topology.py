#!/usr/bin/env python3
"""Two equal-cost paths between a UDP sender and receiver.

The controller chooses upper (s2) or lower (s3). Explicit ports are part of the
lab contract; controller/routing.py uses the same mapping.
"""

import argparse

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo


class DiamondTopo(Topo):
    def build(self, bandwidth=10, delay="5ms", loss=0, datapath="kernel"):
        h1 = self.addHost("h1", ip="10.0.0.1/24", mac="00:00:00:00:00:01")
        h2 = self.addHost("h2", ip="10.0.0.2/24", mac="00:00:00:00:00:02")
        switches = {i: self.addSwitch("s%d" % i, dpid="%016x" % i,
                                      protocols="OpenFlow13", failMode="secure",
                                      datapath=datapath)
                    for i in range(1, 5)}
        # Calculate checksums in the sending kernel. OVS userspace forwarding
        # through veth must not receive partially checksummed UDP packets.
        offloads = dict(txo=False, rxo=False)
        options = dict(bw=bandwidth, delay=delay, loss=loss, use_htb=True, **offloads)
        self.addLink(h1, switches[1], port1=0, port2=1, **offloads)
        self.addLink(switches[1], switches[2], port1=2, port2=1, **options)
        self.addLink(switches[2], switches[4], port1=2, port2=1, **options)
        self.addLink(switches[1], switches[3], port1=3, port2=1, **options)
        self.addLink(switches[3], switches[4], port1=2, port2=2, **options)
        self.addLink(switches[4], h2, port1=3, port2=0, **offloads)


def build_network(controller_port=6653, bandwidth=10, delay="5ms", loss=0,
                  datapath="kernel"):
    """Return an unstarted network; caller owns start(), stop(), and cleanup."""
    if bandwidth <= 0 or not 0 <= loss <= 100:
        raise ValueError("bandwidth must be positive and loss must be in 0..100")
    if datapath not in ("kernel", "user"):
        raise ValueError("datapath must be kernel or user")
    topology = DiamondTopo(bandwidth=bandwidth, delay=delay, loss=loss,
                           datapath=datapath)
    network = Mininet(topo=topology, controller=None, switch=OVSSwitch,
                      link=TCLink, autoSetMacs=False, autoStaticArp=False)
    network.addController("c0", controller=RemoteController,
                          ip="127.0.0.1", port=controller_port)
    return network


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-port", type=int, default=6653)
    parser.add_argument("--bandwidth", type=float, default=10)
    parser.add_argument("--delay", default="5ms")
    parser.add_argument("--loss", type=float, default=0)
    parser.add_argument("--datapath", choices=("kernel", "user"), default="kernel")
    args = parser.parse_args()
    network = build_network(**vars(args))
    try:
        network.start()
        CLI(network)
    finally:
        network.stop()


topos = {"diamond": DiamondTopo}

if __name__ == "__main__":
    main()
