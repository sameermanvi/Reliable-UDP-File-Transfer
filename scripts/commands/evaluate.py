#!/usr/bin/env python3
"""One reproducible rubric evaluation: tests, repeated matrix, plots and evidence index."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def linux_plan(output, datapath, repeats):
    base = [sys.executable, str(ROOT / 'scripts/commands/run_experiments.py'), '--datapath', datapath,
            '--repeats', str(repeats), '--timeout', '180', '--ccs', 'off']
    return [
        base + ['--output', str(output / 'matrix'), '--scenarios', 'normal', 'loss', 'link-failure',
                '--modes', 'static', 'failover', '--rtos', 'fixed', 'adaptive', '--sacks', 'plain', 'bitmap',
                '--loss-rates', '0', '2', '--failure-times', '.5', '1.5', '--file-size', '8388608'],
        base + ['--output', str(output / 'lower-recovery'), '--scenarios', 'link-failure',
                '--modes', 'failover', '--rtos', 'adaptive', '--sacks', 'bitmap', '--initial-path', 'lower',
                '--loss', '0', '--file-size', '8388608'],
        base + ['--output', str(output / 'robustness'), '--scenarios', 'robust', 'soft-degradation',
                '--modes', 'failover', '--rtos', 'adaptive', '--sacks', 'bitmap', '--loss', '2',
                '--flap-periods', '.5', '2', '--reorder', '20', '--file-size', '16777216'],
    ]


def analyze(directory, local=False):
    # Numeric summaries and all failed rows always remain available without Matplotlib.
    subprocess.run([sys.executable, str(ROOT/'scripts/commands/plot_metrics.py'), str(directory/'metrics.csv'),
                    '--output', str(directory/'plots'), '--no-plots'], check=True)
    if local:
        subprocess.run([sys.executable, str(ROOT/'scripts/commands/plot_timeline.py'), '--metrics',
                        str(directory/'metrics.csv'), '--output', str(directory/'plots')], check=True)
    else:
        subprocess.run([sys.executable, str(ROOT/'scripts/commands/plot_metrics.py'), str(directory/'metrics.csv'),
                        '--output', str(directory/'plots')], check=True)
        for controller in directory.glob('*/controller.jsonl'):
            progress = controller.parent/'progress-0.jsonl'
            if progress.exists() and progress.stat().st_size:
                subprocess.run([sys.executable, str(ROOT/'scripts/commands/plot_timeline.py'), '--progress', str(progress),
                                '--controller', str(controller), '--output', str(controller.parent/'plots')], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--datapath', choices=['kernel', 'user'], default='user')
    parser.add_argument('--local-only', action='store_true')
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error('final evaluation requires at least three repetitions; use demo.py for a quick check')
    output = args.output.resolve()
    if not args.local_only and not args.plan_only and (sys.platform != 'linux' or os.geteuid() != 0):
        parser.error('Linux/root required; use --plan-only here, or --local-only for transport evidence')
    output.mkdir(parents=True, exist_ok=False)
    commands = linux_plan(output, args.datapath, args.repeats)
    manifest = dict(status='planned' if args.plan_only else 'running', platform=platform.platform(),
                    repeats=args.repeats, scope='local transport only' if args.local_only else 'Linux SDN rubric evaluation',
                    linux_commands=commands, started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    def save():
        (output/'evaluation.json').write_text(json.dumps(manifest, indent=2)+'\n')
    save()
    if args.plan_only:
        (output/'README.md').write_text('# Pending Linux evaluation\n\nThis directory contains a command plan, not measured results.\n'
            'On a prepared Linux host run `sudo .venv/bin/python scripts/evaluate.py --output results/rubric-final`.\n'
            'Expected: tests.log, evaluation.json, matrix/, lower-recovery/, robustness/, each with CSV/JSON, '
            'plots/summary.md, controller/endpoint/progress logs, hashes and per-trial joined timelines.\n')
        print(output/'evaluation.json')
        return 0
    failed = False
    try:
        with (output/'tests.log').open('w') as log:
            subprocess.run(['make', 'test'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        if args.local_only:
            local = output/'transport'
            command = [sys.executable, str(ROOT/'scripts/commands/benchmark_reliability.py'), '--output', str(local),
                       '--repeats', str(args.repeats)]
            with (output/'benchmark.log').open('w') as log:
                result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            failed = result.returncode != 0
            analyze(local, local=True)
        else:
            for index, command in enumerate(commands):
                with (output/f'runner-{index}.log').open('w') as log:
                    result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                failed |= result.returncode != 0
                directory = Path(command[command.index('--output')+1])
                if (directory/'metrics.csv').exists():
                    analyze(directory)
        manifest['status'] = 'failed' if failed else 'passed'
    except (subprocess.CalledProcessError, OSError) as exc:
        manifest.update(status='failed', error=str(exc)); failed = True
    finally:
        save()
        (output/'README.md').write_text('# Evaluation evidence\n\nStatus: '+manifest['status']+
            '\n\nSee evaluation.json for commands and scope. tests.log records the full automated suite. '
            'Each measured subdirectory retains every trial, hash-verification fields, summaries and plots. '
            'Local-only execution does not validate Linux SDN.\n')
    print('Evaluation:', output, manifest['status'])
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
