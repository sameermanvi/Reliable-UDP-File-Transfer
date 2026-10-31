#!/usr/bin/env python3
"""One assessed live transfer: active-path failure, route evidence and final hash."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / time.strftime('demo-%Y%m%d-%H%M%S'))
    parser.add_argument('--mode', choices=['static', 'failover'], default='failover')
    parser.add_argument('--scenario', choices=['link-failure', 'robust', 'soft-degradation'], default='link-failure')
    parser.add_argument('--initial-path', choices=['upper', 'lower'], default='upper')
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--mib', type=int, default=8)
    parser.add_argument('--datapath', choices=['kernel', 'user'], default='user')
    args = parser.parse_args()
    if args.mib < 1 or args.repetitions < 1:
        parser.error('mib and repetitions must be positive')
    output = args.output.resolve()
    print('1. Start controller + diamond; verify connectivity.\n'
          '2. Transfer starts; wait for real ACK progress.\n'
          '3. Inject active-branch failure (or requested robust/soft scenario).\n'
          '4. Show route decision, resumed progress, SHA-256 result.', flush=True)
    command = [sys.executable, str(ROOT / 'scripts/run_experiments.py'), '--output', str(output),
               '--scenarios', args.scenario, '--modes', args.mode, '--rtos', 'adaptive',
               '--sacks', 'bitmap', '--ccs', 'off', '--repeats', str(args.repetitions),
               '--file-size', str(args.mib * 1024 * 1024), '--fail-after', '.5',
               '--loss', '2' if args.scenario == 'robust' else '0', '--flap-periods', '1',
               '--timeout', '180', '--datapath', args.datapath, '--initial-path', args.initial_path]
    result = subprocess.run(command, cwd=ROOT)
    if (output / 'metrics.csv').exists():
        subprocess.run([sys.executable, str(ROOT / 'scripts/plot_metrics.py'), str(output / 'metrics.csv'),
                        '--output', str(output / 'plots'), '--no-plots'], check=True)
        for trial in output.glob('*/controller.jsonl'):
            progress = trial.parent / 'progress-0.jsonl'
            if progress.exists() and progress.stat().st_size:
                subprocess.run([sys.executable, str(ROOT / 'scripts/plot_timeline.py'),
                                '--progress', str(progress), '--controller', str(trial),
                                '--output', str(trial.parent / 'plots')], check=True)
        print('Evidence:', output, '\nOpen metrics.csv, plots/summary.md and TRIAL/plots/timeline.svg.')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
