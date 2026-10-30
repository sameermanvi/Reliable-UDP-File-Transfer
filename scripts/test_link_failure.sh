#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_bin=${PYTHON:-"$project_dir/.venv/bin/python"}
exec "$python_bin" "$project_dir/scripts/run_experiments.py" \
    --scenarios link-failure --modes static failover --repeats 1 "$@"
