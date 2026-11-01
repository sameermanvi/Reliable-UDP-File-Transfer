#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
if [ -d .venv/bin ]; then default_sdn_bin=.venv/bin; else default_sdn_bin=/opt/sdn/bin; fi
exec "${SDN_BIN:-$default_sdn_bin}/python" mininet/topology.py "$@"
