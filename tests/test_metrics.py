"""Check experiment interpretation independently of Mininet."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "experiments", Path(__file__).resolve().parents[1] / "scripts/run_experiments.py")
experiments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiments)
plot_spec = importlib.util.spec_from_file_location(
    "plots", Path(__file__).resolve().parents[1] / "scripts/plot_metrics.py")
plots = importlib.util.module_from_spec(plot_spec)
plot_spec.loader.exec_module(plots)


class MetricsTests(unittest.TestCase):
    def test_summary_types_and_failed_transfer(self):
        self.assertEqual(experiments.parse_summary("Retry limit reached for DATA 20."), {})
        row = experiments.parse_summary(
            "Transfer complete: bytes=2048 crc32=abcdef01 packets=2 data_sends=3 "
            "retransmits=1 seconds=0.250 goodput_mbps=0.066")
        self.assertEqual(row["crc32"], "abcdef01")
        self.assertEqual(row["retransmits"], 1)
        self.assertEqual(row["seconds"], .25)

    def test_recovery_requires_new_progress_after_route_ready(self):
        progress = [dict(event="ack_progress", monotonic_ns=t, base=b)
                    for t, b in [(900000000, 10), (1050000000, 11),
                                 (1300000000, 12)]]
        routes = [dict(event="route_ready", path="lower", monotonic_ns=1200000000)]
        result = experiments.recovery_metrics(progress, routes, 1000000000)
        self.assertAlmostEqual(result["route_install_seconds"], .2)
        self.assertAlmostEqual(result["progress_recovery_seconds"], .3)
        self.assertAlmostEqual(result["ack_gap_seconds"], .4)
        without_progress = experiments.recovery_metrics(progress[:2], routes, 1000000000)
        self.assertIsNone(without_progress["progress_recovery_seconds"])

    def test_static_or_stale_route_does_not_claim_recovery(self):
        progress = [dict(event="ack_progress", monotonic_ns=200, base=4)]
        for routes in ([], [dict(event="route_ready", path="upper", monotonic_ns=150)],
                       [dict(event="route_ready", path="lower", monotonic_ns=50)]):
            result = experiments.recovery_metrics(progress, routes, 100)
            self.assertIsNone(result["progress_recovery_seconds"])

    def test_partially_written_log_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            self.assertEqual(experiments.read_events(path), [])
            path.write_text('{"event":"one"}\n{"event":')
            self.assertEqual(experiments.read_events(path), [{"event": "one"}])

    def test_failed_runs_count_toward_completion_but_not_goodput(self):
        rows = [dict(scenario="normal", mode="failover", run_id=str(index),
                     success=success, expectation_met=success, goodput_mbps=goodput)
                for index, (success, goodput) in enumerate(
                    [("True", "8"), ("True", "10"), ("False", "0")])]
        result = plots.summarize(rows)[0]
        self.assertEqual(result["observations"], 3)
        self.assertEqual(result["successful"], 2)
        self.assertEqual(result["goodput_mbps"]["mean"], 9)
        self.assertIsNone(result["progress_recovery_seconds"])

    def test_concurrent_flows_are_one_trial_and_missing_values_are_not_zero(self):
        rows = [dict(scenario="link-failure", mode="static", run_id="same-trial",
                     success="False", expectation_met="True") for _ in range(2)]
        result = plots.summarize(rows)[0]
        self.assertEqual(result["trials"], 1)
        self.assertEqual(result["expected_outcomes"], 2)
        self.assertIsNone(result["goodput_mbps"])


if __name__ == "__main__":
    unittest.main()
