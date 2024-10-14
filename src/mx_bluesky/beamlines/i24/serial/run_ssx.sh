#!/bin/bash

# Start the edm screen relative to requested serial collection
expt_type=${1:-FT}

current=$( realpath "$( dirname "$0" )" )
cd $current
cd ../../../..

echo "Activating python environment..."
source .venv/bin/activate

shopt -s nocasematch

if [[ $expt_type == "FT" ]] || [[ $expt_type == "fixed-target" ]]
then
    echo "Starting fixed target edm screen."
    edm -x ./edm_serial/FT-gui/DiamondChipI24-py3v1.edl
elif [[ $expt_type == "EX" ]] || [[ $expt_type == "extruder" ]]
then
    echo "Starting extruder edm screen."
    edm -x ./edm_serial/EX-gui/DiamondExtruder-I24-py3v1.edl
else
    echo "No edm found for $expt_type."
fi

echo "Edm screen closed, deactivate python environment"
deactivate
