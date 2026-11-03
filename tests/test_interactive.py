"""Menu routing and real stage-one endpoint/verification smoke tests."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('interactive', ROOT/'scripts/commands/interactive.py')
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


class InteractiveTests(unittest.TestCase):
    def test_cli_and_alias(self):
        for command in ('interactive','menu'):
            result = subprocess.run([sys.executable,'scripts/run.py',command,'--help'],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--step', result.stdout)

    def test_all_routes_one_through_six(self):
        with patch.object(sys, 'argv', ['interactive','--step','a']), patch.object(menu, 'stage') as stage:
            self.assertEqual(menu.main(), 0)
        self.assertEqual([c.args[0] for c in stage.call_args_list], list(range(1,7)))

    def test_dashboard_launch_uses_existing_cli(self):
        with patch.object(menu, 'run') as run:
            menu.stage(8)
        self.assertEqual(run.call_args.args[0][-4:], ['scripts/run.py','viz','--port','8080'])

    def test_sdn_uses_auto_detected_backend(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT/'results') as folder:
            directory = Path(folder)
            def trial(command, **kwargs):
                self.assertIn('demo', command)
                self.assertIn('--datapath', command)
                (directory/'metrics.csv').write_text(
                    'success,sha256_match,expectation_met,link_down_to_progress_seconds\nTrue,True,True,0.025\n')
            with patch.object(menu, 'output_dir', return_value=directory), patch.object(menu, 'run', side_effect=trial), patch.object(menu, 'open_plot'), contextlib.redirect_stdout(io.StringIO()) as output:
                menu.sdn(backend=([sys.executable,'scripts/run.py'],False))
            self.assertIn('25.000', output.getvalue())

    def test_real_baseline(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            menu.stage(1)
        self.assertIn('CRC32 & SHA-256 MATCH', output.getvalue())


if __name__=='__main__':
    unittest.main()
