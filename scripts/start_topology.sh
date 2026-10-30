#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec "${SDN_BIN:-/opt/sdn/bin}/python" mininet/topology.py "$@"
