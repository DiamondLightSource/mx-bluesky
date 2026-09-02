#!/bin/bash

# Sources the python environment and starts a blueapi server
# on a python IOC to run serial on I24 with procserv

# Get the directory of this script
current_directory=$( realpath "$( dirname "$0" )" )
# Get the directory with the venv
env_directory=$(dirname $current_directory)
# And where the blueapi config lives
config_directory="${env_directory}/src/mx_bluesky/beamlines/i24/serial"

# Source modules environment
source /dls_sw/etc/profile
# Activate virtual environment
source $env_directory/.venv/bin/activate

export LOG_DIR="/dls_sw/i24/logs/bluesky"
export DEBUG_LOG_DIR="$LOG_DIR"

# Start blueapi server
blueapi -c "${config_directory}/blueapi_config.yaml" serve
