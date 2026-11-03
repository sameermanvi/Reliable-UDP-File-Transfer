"""Loopback HTTP controls and a resumable SSE stream for one lab session."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "scripts/visualizer"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from viz_live import run_live
from viz_replay import Playback, list_trials, resolve_trial, run_replay


class Busy(Exception):
    pass


class Session:
    """A disk-backed journal lets slow browsers catch up without stalling UDP."""
    def __init__(self, results):
        self.results = results
        self.changed = threading.Condition()
        self.journal = tempfile.TemporaryFile()
        self.generation = 0
        self.size = 0
        self.mode = None
        self.worker = None
        self.cancel = threading.Event()
        self.loss = threading.Event()
        self.playback = None

    def emit(self, record):
        line = json.dumps(record, separators=(',', ':'), allow_nan=False).encode() + b'\n'
        with self.changed:
            self.journal.seek(self.size)
            self.size += self.journal.write(line)
            self.changed.notify_all()

    def active(self):
        return self.worker is not None and self.worker.is_alive()

    def start(self, mode, options, trial=None):
        with self.changed:
            if self.active():
                raise Busy("Stop the current session before starting another.")
            self.generation += 1
            self.journal.seek(0)
            self.journal.truncate()
            self.size = 0
            self.mode = mode
            self.cancel = threading.Event()
            self.loss = threading.Event()
            self.playback = Playback(speed=options.get('speed', 1)) if trial else None
            self.emit(dict(event='session_start', source='session', mode=mode, **options))

            def run():
                try:
                    if mode == 'live':
                        run_live(options, self.emit, self.cancel, self.loss)
                    else:
                        run_replay(trial, mode == 'follow', self.emit, self.cancel, self.playback)
                    outcome = dict(ok=not self.cancel.is_set())
                except Exception as exc:
                    outcome = dict(ok=False, error=str(exc))
                self.emit(dict(event='session_end', source='session',
                               cancelled=self.cancel.is_set(), **outcome))

            self.worker = threading.Thread(target=run, name='telemetry-' + mode, daemon=True)
            self.worker.start()
            return {'generation': self.generation, 'mode': mode}

    def batch(self, generation, offset):
        with self.changed:
            if generation == self.generation and offset == self.size:
                self.changed.wait(timeout=8)
            if generation != self.generation or offset > self.size:
                offset = 0
            self.journal.seek(offset)
            frames = []
            for line in self.journal.readlines(64 * 1024):
                offset += len(line)
                frames.extend((f'id: {self.generation}:{offset}\ndata: '.encode(), line, b'\n'))
            return self.generation, offset, b''.join(frames) or b': heartbeat\n\n'


def live_options(body):
    options = {}
    for name in ('sack', 'adaptive_rto', 'cc'):
        value = body.get(name, True)
        if type(value) is not bool:
            raise ValueError(f'{name} must be a boolean')
        options[name] = value
    rate = body.get('drop_rate', 0.1)
    if type(rate) not in (float, int) or not math.isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError('drop_rate must be between 0 and 1')
    return dict(options, drop_rate=rate)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def reply(self, status, data, mime='application/json'):
        payload = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if port == 80:
            hosts.update(('127.0.0.1', 'localhost'))
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin')
        if host in hosts and (origin is None or origin == 'http://' + host):
            return True
        self.close_connection = True
        self.reply(403, {'error': 'Only local, same-origin requests are accepted.'})
        return False

    def do_GET(self):
        if not self.allowed():
            return
        session = self.server.session
        path = urlsplit(self.path).path
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'application/javascript'),
                 '/style.css': ('style.css', 'text/css')}
        if path in files:
            name, mime = files[path]
            self.reply(200, (ASSETS/name).read_bytes(), mime)
        elif path == '/api/trials':
            self.reply(200, {'trials': ['results/' + str(t) for t in list_trials(session.results)]})
        elif path == '/api/stream':
            self.stream(session)
        else:
            self.reply(404, {'error': 'Unknown resource'})

    def stream(self, session):
        try:
            generation, offset = map(int, self.headers.get('Last-Event-ID', '0:0').split(':'))
            if min(generation, offset) < 0:
                raise ValueError()
        except ValueError:
            self.reply(400, {'error': 'Invalid stream cursor'})
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.connection.settimeout(15)
        try:
            self.wfile.write(b': connected\n\n')
            while True:
                generation, offset, data = session.batch(generation, offset)
                self.wfile.write(data)
        except (ConnectionError, TimeoutError, ValueError):
            return

    def do_POST(self):
        if not self.allowed():
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if self.headers.get_content_type() != 'application/json' or not 0 < length <= 8192:
                self.close_connection = True
                raise ValueError('Expected a small JSON request body')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected a JSON object')
            result = self.control(urlsplit(self.path).path, body)
        except Busy as exc:
            self.reply(409, {'error': str(exc)})
        except (ValueError, TypeError, FileNotFoundError) as exc:
            self.reply(400, {'error': str(exc)})
        else:
            self.reply(200, result)

    def control(self, path, body):
        session = self.server.session
        if path == '/api/start':
            return session.start('live', live_options(body))
        if path == '/api/replay-trial':
            requested = body.get('trial')
            follow = body.get('follow', False)
            speed = body.get('speed', 1)
            if not isinstance(requested, str) or not requested.strip() or type(follow) is not bool:
                raise ValueError('Expected a trial path and boolean follow option')
            if type(speed) not in (float, int) or speed not in (.25, .5, 1):
                raise ValueError('Select 0.25x, 0.5x or 1x')
            trial = resolve_trial(session.results, requested, follow=follow)
            trial.resolve().relative_to(session.results.resolve())
            return session.start('follow' if follow else 'replay',
                                 dict(trial='results/' + trial.relative_to(session.results).as_posix(),
                                      speed=speed), trial)
        with session.changed:
            if not session.active():
                raise Busy('No active session')
            if path == '/api/stop':
                session.cancel.set()
            elif path == '/api/inject-loss' and session.mode == 'live':
                session.loss.set()
            elif path == '/api/playback' and session.playback:
                session.playback.control(body.get('action'), body.get('speed'))
            else:
                raise ValueError('Control unavailable in this mode')
            return {'ok': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--no-browser', action='store_true', help='Print the URL without opening a browser')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('port must be between 0 and 65535')
    subprocess.run(['make'], cwd=ROOT, check=True)
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        server.session = Session(ROOT/'results')
        url = f'http://127.0.0.1:{server.server_port}/'
        print(f'Telemetry console at {url}', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.session.cancel.set()
            if server.session.worker:
                server.session.worker.join(timeout=10)
            server.session.journal.close()


if __name__ == '__main__':
    main()
