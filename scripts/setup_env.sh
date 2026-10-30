#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$(uname -s)" != Linux ] || [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo on Ubuntu 22.04, or use the supplied Dockerfile." >&2
    exit 1
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y build-essential python3 python3-venv python3-pip mininet \
    openvswitch-switch iproute2 iputils-ping net-tools procps python3-matplotlib ethtool
python3 -m venv --system-site-packages "$project_dir/.venv"
"$project_dir/.venv/bin/python" -m pip install --timeout 120 -r "$project_dir/requirements-sdn.txt"
make -C "$project_dir/src"
service openvswitch-switch start
echo "Ready: sudo $project_dir/.venv/bin/python $project_dir/scripts/run_experiments.py --help"
