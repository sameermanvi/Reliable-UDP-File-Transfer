#!/bin/sh
exec sh "$(dirname "$0")/docker/setup_env.sh" "$@"
