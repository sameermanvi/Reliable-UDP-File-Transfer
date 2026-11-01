#!/usr/bin/env python3
"""Run the UDP lab demos, benchmarks, and plots."""
import argparse
import runpy
from pathlib import Path
import sys

COMMANDS = {
    "demo": "demo", "evaluate": "evaluate", "benchmark": "benchmark_reliability",
    "experiment": "run_experiments", "plot": "plot_metrics", "timeline": "plot_timeline",
}

def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="Use COMMAND --help for command options.")
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args(sys.argv[1:2])
    script = Path(__file__).resolve().parent / "commands" / (COMMANDS[args.command] + ".py")
    sys.argv = [str(script), *sys.argv[2:]]
    runpy.run_path(str(script), run_name="__main__")

if __name__ == "__main__":
    main()
