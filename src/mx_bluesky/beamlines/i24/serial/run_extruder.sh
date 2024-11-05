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

# Get the directory of this script
current=$( realpath "$( dirname "$0" )" )

if [[ $NO_PROCESERV_TEST == true ]]; then
    echo "Start the blueapi sever"

    # Run script to start blueapi serve
    . $current/start_blueapi.sh
fi

echo "Set up logging configuration"
blueapi -c "${current}/blueapi_config.yaml" controller run setup_collection_logs '{"expt":"Serial Jet"}'

# Open the edm screen for an extruder serial collection
echo "Starting extruder edm screen."
edm -x "${edm_path}/EX-gui/DiamondExtruder-I24-py3v1.edl"

echo "Edm screen closed"

echo "Clean up log configuration"
blueapi -c "${current}/blueapi_config.yaml" controller run clean_up_log_config_at_end

if [[ $NO_PROCESERV_TEST == true ]]; then
    # In this case blueapi server needs to be killed.
    pgrep blueapi | xargs kill
    echo "Blueapi process killed"
fi

echo "All done, bye!"
