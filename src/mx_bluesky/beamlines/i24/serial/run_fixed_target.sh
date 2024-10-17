#!/bin/bash

NO_PROCESERV_TEST=false

case "$2" in
    -t | --test)
        echo "Will run serial in test mode without procserv."
        NO_PROCESERV_TEST=true
        ;;
esac

# Get edm path from input
edm_path=$1

# Export env variable for the stages edm to work properly
export EDMDATAFILES="/dls_sw/prod/R3.14.12.3/support/motor/6-7-1dls14/motorApp/opi/edl"

if [[ $NO_PROCESERV_TEST == true ]]; then
    echo "Start the blueapi sever"

    # Get the directory of this script
    current=$( realpath "$( dirname "$0" )" )

    # Run script to start blueapi serve
    . $current/start_blueapi.sh
fi

# Open the edm screen for a fixed target serial collection
echo "Starting fixed target edm screen."
edm -x "${edm_path}/FT-gui/DiamondChipI24-py3v1.edl"

echo "Edm screen closed, bye!"

if [[ $NO_PROCESERV_TEST == true ]]; then
    # In this case blueapi server needs to be killed.
    pgrep blueapi | xargs kill
    echo "Blueapi process killed"
fi
