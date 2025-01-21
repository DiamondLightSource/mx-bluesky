#!/bin/bash
# Run the system test image locally in podman for debugging
# to remove the runner
# podman compose -f $PROJECTDIR/utility_scripts/docker/system-test-compose.yml down
PROJECTDIR=$(realpath $(dirname $0)/..)
SECRETS_DIR=$HOME/.secrets podman compose -f $PROJECTDIR/utility_scripts/docker/system-test-compose.yml up -d
