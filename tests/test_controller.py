"""Routing checks that run without Mininet, OVS, root, or OS-Ken."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller.routing import HOST_PORTS, PATH_PORTS, PathPolicy, forwarding_rules


def connected_policy(mode="failover"):
    policy = PathPolicy(mode)
    policy.connected.update((1, 2, 3, 4))
    for port in HOST_PORTS + PATH_PORTS["upper"] + PATH_PORTS["lower"]:
        policy.ports[port] = True
    return policy


# Independent wiring model, including the terminal host ports. A packet reaching
# either host leaves the graph. Use it to trace real forwarding decisions.
WIRES = {
    (1, 1): "h1", (4, 3): "h2",
    (1, 2): (2, 1), (2, 1): (1, 2),
    (2, 2): (4, 1), (4, 1): (2, 2),
    (1, 3): (3, 1), (3, 1): (1, 3),
    (3, 2): (4, 2), (4, 2): (3, 2),
}


def trace(rules, start, eth_type):
    cursor = start
    visited = []
    while isinstance(cursor, tuple):
        if cursor in visited:
            raise AssertionError("forwarding loop: %r" % (visited + [cursor]))
        visited.append(cursor)
        dpid, in_port = cursor
        matches = [rule for rule in rules[dpid]
                   if rule.in_port == in_port and rule.eth_type == eth_type]
        if len(matches) != 1:
            raise AssertionError("expected exactly one matching rule")
        out_port = matches[0].out_port
        if out_port is None:
            return None, visited
        cursor = WIRES[(dpid, out_port)]
    return cursor, visited


class RoutingTests(unittest.TestCase):
    def test_primary_path_and_each_endpoint_failure(self):
        self.assertEqual(connected_policy().choose(None), "upper")
        for endpoint in PATH_PORTS["upper"]:
            with self.subTest(endpoint=endpoint):
                policy = connected_policy()
                policy.ports[endpoint] = False
                self.assertEqual(policy.choose("upper"), "lower")

    def test_backup_failure_does_not_move_healthy_transfer(self):
        policy = connected_policy()
        policy.ports[(1, 3)] = False
        self.assertEqual(policy.choose("upper"), "upper")

    def test_no_automatic_failback_and_recovery_after_second_failure(self):
        policy = connected_policy()
        policy.ports[(1, 2)] = False
        self.assertEqual(policy.choose("upper"), "lower")
        policy.ports[(1, 2)] = True
        self.assertEqual(policy.choose("lower"), "lower")
        policy.ports[(3, 2)] = False
        self.assertEqual(policy.choose("lower"), "upper")

    def test_both_paths_down_and_restoration(self):
        policy = connected_policy()
        policy.ports[(1, 2)] = policy.ports[(4, 2)] = False
        self.assertIsNone(policy.choose("upper"))
        policy.ports[(4, 2)] = True
        self.assertEqual(policy.choose(None), "lower")

    def test_switch_and_host_failure(self):
        policy = connected_policy()
        policy.connected.remove(2)
        self.assertEqual(policy.choose("upper"), "lower")
        policy.connected.remove(4)
        self.assertIsNone(policy.choose("lower"))
        policy = connected_policy()
        policy.ports[(1, 1)] = False
        self.assertIsNone(policy.choose("upper"))

    def test_static_baseline_keeps_failed_path(self):
        policy = connected_policy("static")
        policy.ports[(1, 2)] = False
        self.assertEqual(policy.choose("upper"), "upper")
        self.assertTrue(policy.available("lower"))
        self.assertFalse(policy.available("upper"))

    def test_arp_and_ipv4_reach_correct_hosts_on_each_path(self):
        for path, middle in (("upper", 2), ("lower", 3)):
            for eth_type in (0x0800, 0x0806):
                with self.subTest(path=path, eth_type=eth_type):
                    rules = forwarding_rules(path)
                    host, visits = trace(rules, (1, 1), eth_type)
                    self.assertEqual(host, "h2")
                    self.assertEqual([dpid for dpid, _ in visits], [1, middle, 4])
                    host, visits = trace(rules, (4, 3), eth_type)
                    self.assertEqual(host, "h1")
                    self.assertEqual([dpid for dpid, _ in visits], [4, middle, 1])

    def test_partial_edge_update_is_loop_free(self):
        # OpenFlow updates reach different switches at different times. Either
        # ingress can change first, so test both mixed configurations.
        for first in ("upper", "lower"):
            second = "lower" if first == "upper" else "upper"
            rules = forwarding_rules(first)
            rules[4] = forwarding_rules(second)[4]
            for eth_type in (0x0800, 0x0806):
                self.assertEqual(trace(rules, (1, 1), eth_type)[0], "h2")
                self.assertEqual(trace(rules, (4, 3), eth_type)[0], "h1")

    def test_unavailable_route_drops_host_ingress(self):
        rules = forwarding_rules(None)
        for eth_type in (0x0800, 0x0806):
            self.assertIsNone(trace(rules, (1, 1), eth_type)[0])
            self.assertIsNone(trace(rules, (4, 3), eth_type)[0])

    def test_health_hysteresis_and_unknown_backup(self):
        policy = connected_policy()
        policy.health = {"upper": .1}
        self.assertEqual(policy.choose("upper"), "upper")
        policy.health["lower"] = .09
        self.assertEqual(policy.choose("upper"), "upper")
        policy.health["lower"] = .01
        self.assertEqual(policy.choose("upper"), "lower")
        policy.ports[(1, 3)] = False
        self.assertEqual(policy.choose("upper"), "upper")

    def test_lower_initial_route_and_static_contrast(self):
        policy = connected_policy()
        policy.initial = "lower"
        self.assertEqual(policy.choose(None), "lower")
        policy.mode = "static"
        policy.ports[(1, 3)] = False
        self.assertEqual(policy.choose("lower"), "lower")

    def test_invalid_configuration_rejected(self):
        with self.assertRaises(ValueError):
            PathPolicy("typo")
        with self.assertRaises(ValueError):
            forwarding_rules("typo")


if __name__ == "__main__":
    unittest.main()
