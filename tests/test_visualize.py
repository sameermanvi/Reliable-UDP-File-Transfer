"""Exercise real C transfer telemetry and HTTP controls."""
from pathlib import Path
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/commands'))
from visualize import Handler, Session, ThreadingHTTPServer
from viz_replay import Playback, resolve_trial, run_replay


class VisualizeTests(unittest.TestCase):
    def test_live_http_and_integrity(self):
        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            server.session = Session(ROOT/'results')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = 'http://127.0.0.1:' + str(server.server_port)
            try:
                self.assertIn(b'PROTOCOL CONSOLE', urllib.request.urlopen(base).read())
                request = urllib.request.Request(base+'/api/start', data=b'{"drop_rate":0}',
                                                 headers={'Content-Type':'application/json'})
                self.assertEqual(urllib.request.urlopen(request).status, 200)
                server.session.loss.set()
                server.session.worker.join(45)
                self.assertFalse(server.session.worker.is_alive())
                _, _, raw = server.session.batch(0, 0)
                # Read all batches, including the real final integrity record.
                server.session.journal.seek(0)
                records = [json.loads(line) for line in server.session.journal]
                self.assertTrue(records[-1]['ok'], records[-1])
                self.assertTrue(next(r for r in records if r['event']=='verification')['sha256_match'])
                self.assertTrue(any(r['event']=='dropped_gap' for r in records))
                self.assertTrue(any(r['event']=='ring_snapshot' and len(r['slots'])==32 for r in records))
                self.assertTrue(any(r['event']=='frame' and len(r['header_hex'])==48 for r in records))
                self.assertIn(b'data:', raw)
            finally:
                server.session.cancel.set()
                server.session.worker.join(5)
                server.shutdown()
                thread.join()
                server.session.journal.close()

    def test_replay_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            trial = root/'trial'
            trial.mkdir()
            (trial/'controller.jsonl').write_text('{"event":"route_ready","monotonic_ns":1}\n')
            with self.assertRaises(ValueError):
                resolve_trial(root, '../')
            records = []
            run_replay(trial, False, records.append, threading.Event(), Playback())
            self.assertEqual(records[0]['event'], 'route_ready')
            playback = Playback()
            playback.control('pause')
            playback.control('step')
            self.assertTrue(playback.wait(100, threading.Event()))
            self.assertTrue(playback.paused)


if __name__ == '__main__':
    unittest.main()
