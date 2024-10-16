#!/bin/bash

# Starts a blueapi server on a python IOC to run with procserv

# Get the directory of this script
current_directory=$( realpath "$( dirname "$0" )" )
cd $current_directory

# Source modules environment
source /dls_sw/etc/profile

# Activate virtual environment
source $current_directory/.venv/bin/activate

# Start blueapi server
blueapi -c "${current_directory}/blueapi_config.yaml" serve
