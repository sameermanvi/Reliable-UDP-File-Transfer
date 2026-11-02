"""Tests for adaptive probe scheduling."""

import unittest

from controller.probe_schedule import AdaptiveProbeSchedule


class AdaptiveProbeScheduleTests(unittest.TestCase):
    def setUp(self):
        self.schedule = AdaptiveProbeSchedule()
        self.now = 10_000_000_000

    def test_starts_at_stable_interval(self):
        self.assertEqual(
            self.schedule.interval_ns(self.now),
            AdaptiveProbeSchedule.STABLE_NS,
        )

    def test_failure_increases_probe_frequency(self):
        self.schedule.record_result(False, self.now)

        self.assertEqual(
            self.schedule.interval_ns(self.now),
            AdaptiveProbeSchedule.FAILURE_NS,
        )

    def test_three_successes_enter_recovery_period(self):
        self.schedule.record_result(False, self.now)

        for i in range(3):
            self.schedule.record_result(True, self.now + (i + 1) * 100_000_000)

        recovery_time = self.now + 300_000_000

        self.assertEqual(
            self.schedule.interval_ns(recovery_time),
            AdaptiveProbeSchedule.RECOVERY_NS,
        )

        self.assertEqual(
            self.schedule.interval_ns(
                recovery_time + AdaptiveProbeSchedule.RECOVERY_HOLD_NS
            ),
            AdaptiveProbeSchedule.STABLE_NS,
        )

    def test_another_failure_resets_recovery(self):
        self.schedule.record_result(False, self.now)

        for i in range(3):
            self.schedule.record_result(True, self.now + (i + 1) * 100_000_000)

        self.schedule.record_result(False, self.now + 400_000_000)

        self.assertEqual(
            self.schedule.interval_ns(self.now + 400_000_000),
            AdaptiveProbeSchedule.FAILURE_NS,
        )

    def test_degraded_health_uses_uncertain_interval(self):
        self.schedule.set_degraded(True, self.now)

        self.assertEqual(
            self.schedule.interval_ns(self.now),
            AdaptiveProbeSchedule.UNCERTAIN_NS,
        )

    def test_recovered_health_has_temporary_faster_interval(self):
        self.schedule.set_degraded(True, self.now)
        self.schedule.set_degraded(False, self.now + 100_000_000)

        self.assertEqual(
            self.schedule.interval_ns(self.now + 100_000_000),
            AdaptiveProbeSchedule.RECOVERY_NS,
        )

        self.assertEqual(
            self.schedule.interval_ns(
                self.now + 100_000_000
                + AdaptiveProbeSchedule.RECOVERY_HOLD_NS
            ),
            AdaptiveProbeSchedule.STABLE_NS,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
