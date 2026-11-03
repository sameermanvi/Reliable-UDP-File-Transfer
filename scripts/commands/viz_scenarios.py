"""Guided presets choose real transport options or verified recorded SDN trials."""
import json
import os
from viz_live import run_live
from viz_replay import run_replay

def options(number):
    basic = number == 2
    return dict(sack=not basic, adaptive_rto=not basic, cc=not basic,
                drop_rate=0 if number == 1 else .10)

def select_trial(root, number):
    mode = 'failover' if number == 5 else 'static'
    preferred = root/('live-failover' if number == 5 else 'live-static')
    candidates = sorted(preferred.rglob('metrics.json')) if preferred.exists() else []
    candidates += sorted((root/'rubric-final').rglob('metrics.json'))
    for path in candidates:
        path.resolve().relative_to(root.resolve())
        data = json.loads(path.read_text())
        rows = data if isinstance(data, list) else [data]
        if not rows:
            continue
        row = rows[0]
        if (row.get('scenario') == 'link-failure' and row.get('mode') == mode
                and row.get('initial_path') == 'upper'
                and row.get('expectation_met') is True
                and (row.get('sha256_match') is True if number == 5 else row.get('success') is False)
                and (path.parent/'controller.jsonl').exists()):
            return path.parent, row
    raise ValueError('No verified '+mode+' link-cut trial found under results/')

class Unpaced:
    """The browser owns visual timing while this producer preserves record timestamps."""
    def wait(self, seconds, stop):
        return not stop.is_set()

def run_scenario(number, root, emit, stop, loss, packets=32):
    def transfer(variant, output, payload=None):
        config = dict(options(variant), packets=packets)
        if variant != 1:
            config['drop_sequences'] = [n for n in range(packets-1) if n % 32 in (4,14,23)]
        records = []
        try:
            run_live(config, records.append, stop, loss, payload=payload)
        finally:
            for record in sorted(records, key=lambda r: r['monotonic_ns']):
                output(record)

    if number in (1,2,3):
        transfer(number, emit)
    elif number == 4:
        payload = os.urandom(packets*1024)
        for variant in (2,3):
            if stop.is_set():
                return
            emit(dict(event='variant_start', source='session', variant=variant, **options(variant)))
            def tagged(record):
                emit(dict(record, variant=variant))
            transfer(variant, tagged, payload)
    else:
        trial, metrics = select_trial(root, number)
        emit(dict(event='trial_metadata', source='session', file_bytes=metrics['file_bytes'],
                  trial='results/'+trial.relative_to(root).as_posix(), metrics=metrics))
        run_replay(trial, False, emit, stop, Unpaced())
