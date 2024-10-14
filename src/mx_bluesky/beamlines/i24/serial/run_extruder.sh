#!/bin/bash

# Get edm path from input
edm_path=$1

# Get the directory of this script
current=$( realpath "$( dirname "$0" )" )

# Run script to start blueapi serve
. $current/start_blueapi.sh

# Open the edm screen for an extruder serial collection
echo "Starting extruder edm screen."
edm -x "${edm_path}/EX-gui/DiamondExtruder-I24-py3v1.edl"

echo "Edm screen closed, bye!"

pgrep blueapi | xargs kill
echo "Blueapi process killed"
