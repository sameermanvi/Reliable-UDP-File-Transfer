"""Monotonic-clock playback of recorded or growing lab JSONL files."""
import json
from pathlib import Path
import threading
import time


class Playback:
    def __init__(self, speed=1, paused=False):
        self.speed, self.paused, self.steps = speed, paused, 0
        self.lock = threading.Lock()

    def control(self, action, speed=None):
        with self.lock:
            if action == 'speed':
                if speed not in (.25, .5, 1):
                    raise ValueError('Invalid speed')
                self.speed = speed
            elif action in ('play', 'pause'):
                self.paused = action == 'pause'
            elif action == 'step':
                self.paused = True
                self.steps += 1
            else:
                raise ValueError('Unknown playback action')

    def wait(self, seconds, stop):
        while not stop.is_set():
            with self.lock:
                if self.steps:
                    self.steps -= 1
                    return True
                paused, speed = self.paused, self.speed
            if not paused:
                if seconds <= 0:
                    return True
                seconds -= .01 * speed
            stop.wait(.01)
        return False


def list_trials(root):
    return sorted({p.parent.relative_to(root).as_posix()
                   for p in root.rglob('controller.jsonl')})


def resolve_trial(root, requested, follow=False):
    root = root.resolve()
    requested = requested.removeprefix('results/')
    path = (root/requested).resolve()
    path.relative_to(root)
    if not path.is_dir():
        raise ValueError('Trial directory does not exist')
    if (path/'controller.jsonl').exists():
        return path
    trials = list(path.rglob('controller.jsonl'))
    if not trials:
        if follow:
            return path
        raise ValueError('No controller events in this directory')
    trials.sort(key=lambda p: ('link-failure-failover' not in str(p), str(p)))
    return trials[0].parent


def run_replay(trial, follow, emit, stop_event, playback):
    offsets = {}
    previous = None
    link_down = route_ready = None
    while not stop_event.is_set():
        if follow and not (trial/'controller.jsonl').exists():
            candidates = sorted(trial.rglob('controller.jsonl'))
            if candidates:
                trial = candidates[0].parent
        records = []
        for path in sorted(trial.glob('*.jsonl')):
            role = 'controller' if path.name == 'controller.jsonl' else 'receiver' if path.name.startswith('receiver') else 'sender'
            with path.open() as stream:
                stream.seek(offsets.get(path, 0))
                while True:
                    position = stream.tell()
                    line = stream.readline()
                    if not line or not line.endswith('\n'):
                        offsets[path] = position
                        break
                    record = json.loads(line)
                    if 'monotonic_ns' in record:
                        records.append(dict(record, source=role))
        records.sort(key=lambda r: r['monotonic_ns'])
        for record in records:
            stamp = record['monotonic_ns']
            gap = max(0, (stamp-previous)/1e9) if previous is not None else 0
            if not playback.wait(0 if follow else gap, stop_event):
                return
            emit(record)
            if record.get('event') == 'link_down':
                link_down, route_ready = stamp, None
            elif record.get('event') == 'route_ready' and link_down is not None and stamp > link_down:
                route_ready = stamp
            elif (record.get('event') == 'ack_progress' and route_ready is not None
                  and stamp > route_ready):
                emit(dict(event='recovery', source='replay', monotonic_ns=stamp,
                          link_down_to_ack_ms=(stamp-link_down)/1e6,
                          route_to_ack_ms=(stamp-route_ready)/1e6))
                link_down = route_ready = None
            previous = stamp
        if not follow:
            for name in ('network-initial.txt', 'network-final.txt'):
                snapshot = trial/name
                if snapshot.exists():
                    emit(dict(event='flow_snapshot', source='controller',
                              snapshot=name, rules=snapshot.read_text()))
            metrics = trial/'metrics.json' 
            if metrics.exists():
                emit(dict(event='recorded_metrics', source='replay', metrics=json.loads(metrics.read_text())))
            return
        stop_event.wait(.1)
