#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec "${SDN_BIN:-/opt/sdn/bin}/osken-manager" --ofp-tcp-listen-port 6653 controller/failover.py "$@"
