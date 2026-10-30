"""Small routing policy shared by the controller and its unit tests.

The topology deliberately uses explicit ports. Both branches carry transit
traffic, but each host-facing ingress selects exactly one branch. ARP therefore
follows the same path as IPv4 without flooding around the diamond.
"""

from dataclasses import dataclass


SWITCHES = frozenset((1, 2, 3, 4))
HOST_PORTS = ((1, 1), (4, 3))
PATH_PORTS = {
    "upper": ((1, 2), (2, 1), (2, 2), (4, 1)),
    "lower": ((1, 3), (3, 1), (3, 2), (4, 2)),
}
PATH_SWITCHES = {"upper": (1, 2, 4), "lower": (1, 3, 4)}


@dataclass(frozen=True)
class Flow:
    in_port: int
    eth_type: int
    out_port: int | None


def forwarding_rules(path):
    """Return exact-port IPv4/ARP forwarding rules; None blocks host ingress."""
    if path not in (None, "upper", "lower"):
        raise ValueError("unknown path")
    first = {"upper": 2, "lower": 3, None: None}[path]
    last = {"upper": 1, "lower": 2, None: None}[path]
    port_pairs = {
        1: ((1, first), (2, 1), (3, 1)),
        2: ((1, 2), (2, 1)),
        3: ((1, 2), (2, 1)),
        4: ((1, 3), (2, 3), (3, last)),
    }
    return {
        dpid: [Flow(source, eth_type, destination)
               for source, destination in pairs
               for eth_type in (0x0800, 0x0806)]
        for dpid, pairs in port_pairs.items()
    }


class PathPolicy:
    def __init__(self, mode="failover"):
        if mode not in ("static", "failover"):
            raise ValueError("mode must be static or failover")
        self.mode = mode
        self.connected = set()
        self.ports = {}

    def available(self, path):
        return (all(dpid in self.connected for dpid in PATH_SWITCHES[path])
                and all(self.ports.get(port, False)
                        for port in HOST_PORTS + PATH_PORTS[path]))

    def choose(self, current):
        # A static route intentionally does not recover from a branch failure.
        # Host loss, however, leaves no usable endpoint in either mode.
        if not all(dpid in self.connected for dpid in (1, 4)):
            return None
        if not all(self.ports.get(port, False) for port in HOST_PORTS):
            return None
        if self.mode == "static":
            return "upper"
        if current is not None and self.available(current):
            return current
        for path in ("upper", "lower"):
            if self.available(path):
                return path
        return None
