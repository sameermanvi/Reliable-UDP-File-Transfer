import unittest

from controller.multipath import MultipathScheduler


class MultipathTests(unittest.TestCase):

    def test_alternates_between_healthy_paths(self):
        scheduler = MultipathScheduler()

        selected = [scheduler.select_path() for _ in range(6)]

        self.assertEqual(
            selected,
            ["upper", "lower", "upper", "lower", "upper", "lower"],
        )

    def test_unhealthy_path_is_not_selected(self):
        scheduler = MultipathScheduler()
        scheduler.update_path("upper", healthy=False)

        selected = [scheduler.select_path() for _ in range(4)]

        self.assertEqual(
            selected,
            ["lower", "lower", "lower", "lower"],
        )

    def test_weighted_schedule(self):
        scheduler = MultipathScheduler()
        scheduler.update_path("upper", weight=2)

        selected = [scheduler.select_path() for _ in range(6)]

        self.assertEqual(selected.count("upper"), 4)
        self.assertEqual(selected.count("lower"), 2)

    def test_all_paths_unhealthy(self):
        scheduler = MultipathScheduler()
        scheduler.update_path("upper", healthy=False)
        scheduler.update_path("lower", healthy=False)

        self.assertIsNone(scheduler.select_path())

    def test_weighted_schedule_respects_configured_ratio(self):
        scheduler = MultipathScheduler()
        scheduler.update_path("upper", weight=3)
        scheduler.update_path("lower", weight=1)

        selected = [scheduler.select_path() for _ in range(8)]

        self.assertEqual(selected.count("upper"), 6)
        self.assertEqual(selected.count("lower"), 2)

    def test_recovered_path_returns_to_schedule(self):
        scheduler = MultipathScheduler()
        scheduler.update_path("upper", healthy=False)

        self.assertEqual(scheduler.select_path(), "lower")

        scheduler.update_path("upper", healthy=True)

        selected = [scheduler.select_path() for _ in range(4)]

        self.assertCountEqual(
            selected,
            ["upper", "upper", "lower", "lower"],
        )


if __name__ == "__main__":
    unittest.main()
