"""Exercise the policy used by the real DSCP rule installer."""
from pathlib import Path
import sys
import unittest
import os
import shlex
import subprocess
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller.multipath import eligible_paths
from test_controller import connected_policy


class MultipathTests(unittest.TestCase):
    def setUp(self):
        self.policy = connected_policy()
        self.policy.health = {"upper": .01, "lower": .01}

    def test_real_sender_marks_weights_retries_and_resets(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder)/'sender-test'
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=c11', '-D_POSIX_C_SOURCE=200809L', '-Wall', '-Wextra',
                '-Wpedantic', '-Werror', str(root/'tests/multipath_sender.c'),
                str(root/'src/utils.c'), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=5)

    def test_healthy_paths_share_data(self):
        self.assertEqual(eligible_paths(self.policy, "upper"), {"upper", "lower"})

    def test_degraded_path_is_excluded(self):
        self.policy.health["upper"] = .5
        self.assertEqual(eligible_paths(self.policy, "lower"), {"lower"})

    def test_unmeasured_alternate_is_excluded(self):
        del self.policy.health["lower"]
        self.assertEqual(eligible_paths(self.policy, "upper"), {"upper"})

    def test_failed_path_is_excluded(self):
        self.policy.ports[(1, 2)] = False
        self.assertEqual(eligible_paths(self.policy, "lower"), {"lower"})

    def test_static_mode_has_no_overrides(self):
        self.policy.mode = "static"
        self.assertFalse(eligible_paths(self.policy, "upper"))

    def test_no_selected_route_has_no_overrides(self):
        self.assertFalse(eligible_paths(self.policy, None))


if __name__ == "__main__":
    unittest.main()
