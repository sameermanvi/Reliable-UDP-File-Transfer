import unittest

from controller.probe_schedule import AdaptiveProbeSchedule


class AdaptiveProbeScheduleTests(unittest.TestCase):
    def test_starts_at_250ms(self):
        scheduler = AdaptiveProbeSchedule()
        self.assertEqual(scheduler.interval, 0.25)

    def test_degraded_schedule_uses_fast_interval(self):
        scheduler = AdaptiveProbeSchedule()
        scheduler.set_degraded(True)
        self.assertEqual(scheduler.interval_seconds(0), 0.25)

    def test_failed_probe_halves_interval(self):
        scheduler = AdaptiveProbeSchedule()
        scheduler.record_result(False, now_ns=1_000_000_000)
        self.assertEqual(scheduler.interval, 0.125)

    def test_healthy_schedule_can_increase_interval(self):
        scheduler = AdaptiveProbeSchedule()
        scheduler.set_degraded(False)
        scheduler.record_result(True, now_ns=1_000_000_000)
        self.assertAlmostEqual(scheduler.interval, 0.3125)

    def test_interval_never_exceeds_maximum(self):
        scheduler = AdaptiveProbeSchedule()
        scheduler.set_degraded(False)
        for i in range(30):
            scheduler.record_result(True, now_ns=i * 1_000_000_000)
        self.assertLessEqual(scheduler.interval, scheduler.max_interval)

    def test_interval_never_falls_below_minimum(self):
        scheduler = AdaptiveProbeSchedule()
        for i in range(30):
            scheduler.record_result(False, now_ns=i * 1_000_000_000)
        self.assertGreaterEqual(scheduler.interval, scheduler.min_interval)

    def test_degraded_interval_is_capped_at_250ms(self):
        scheduler = AdaptiveProbeSchedule()
        scheduler.set_degraded(True)
        scheduler.interval = 1.0
        self.assertEqual(scheduler.interval_seconds(0), 0.25)

    def test_initial_interval_is_within_bounds(self):
        scheduler = AdaptiveProbeSchedule()
        self.assertGreaterEqual(scheduler.interval, scheduler.min_interval)
        self.assertLessEqual(scheduler.interval, scheduler.max_interval)


if __name__ == "__main__":
    unittest.main()
