"""Probe validation, bidirectional health, expiry and soft/hard route decisions."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller.probes import ProbeTracker, ENDPOINTS
from test_controller import connected_policy


class ProbeTests(unittest.TestCase):
    def test_both_branches_and_both_directions(self):
        tracker = ProbeTracker()
        now = 1_000_000_000
        for _ in range(4):
            for (path, direction), (_, _, dp, port) in ENDPOINTS.items():
                frame = tracker.send(path, direction, now)
                self.assertIsNone(tracker.receive(frame, 9, port, now+1))
                result = tracker.receive(frame, dp, port, now+20_000_000)
                self.assertTrue(result['success'])
                self.assertIsNone(tracker.receive(frame, dp, port, now+21_000_000))
            now += 100_000_000
        self.assertEqual(set(tracker.scores(now)), {'upper', 'lower'})
        self.assertEqual(tracker.scores(now)['upper'], .02)
        self.assertEqual(tracker.scores(now+3_000_000_000), {})

    def test_soft_degradation_hysteresis_and_recovery(self):
        tracker = ProbeTracker(); policy = connected_policy()
        now = 1_000_000_000
        for _ in range(8):
            for (path, direction), (_, _, dp, port) in ENDPOINTS.items():
                frame = tracker.send(path, direction, now)
                if path == 'lower': tracker.receive(frame, dp, port, now+10_000_000)
            tracker.expire(now+500_000_000)
            now += 600_000_000
        policy.health = tracker.scores(now)
        self.assertEqual(policy.choose('upper'), 'lower')
        policy.ports[(1, 3)] = False
        self.assertEqual(policy.choose('lower'), 'upper')  # health never overrides availability
        tracker.invalidate_port(1, 2)
        self.assertNotIn('upper', tracker.scores(now))

    def test_wrong_session_truncated_late_and_counters(self):
        tracker = ProbeTracker(); frame = tracker.send('upper', 'forward', 100)
        forged = bytearray(frame); forged[22] ^= 1
        for wire in (b'', frame[:30], bytes(forged)):
            self.assertIsNone(tracker.receive(wire, 4, 1, 101))
        self.assertIsNone(tracker.receive(frame, 4, 1, 500_000_100))
        self.assertEqual(len(tracker.expire(500_000_100)), 1)
        self.assertEqual(tracker.expire(500_000_101), [])
        self.assertIsNone(tracker.receive(frame, 4, 1, 500_000_101))
        self.assertEqual(tracker.samples[('upper', 'forward')]['count'], 1)

    def test_repeated_hard_failures_restore_either_path(self):
        policy = connected_policy(); active = 'upper'
        for _ in range(4):
            failed = (1, 2) if active == 'upper' else (1, 3)
            policy.ports[failed] = False
            replacement = policy.choose(active)
            self.assertNotEqual(replacement, active)
            self.assertTrue(policy.available(replacement))
            policy.ports[failed] = True
            self.assertEqual(policy.choose(replacement), replacement)
            active = replacement


if __name__ == '__main__':
    unittest.main(verbosity=2)
