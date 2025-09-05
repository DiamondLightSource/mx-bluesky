#!/bin/bash

NO_PROCESERV_TEST=false

case "$2" in
    -t | --test)
        echo "Will run serial in test mode without procserv."
        NO_PROCESERV_TEST=true
        ;;
esac

# Get visit from PV and set the instrument session thet will be read by the edms
# Hack to make the blueapi CLI happy as the client now requires an instrument session
# on every POST request. For the command line, that means a -i $INSTRUMENT_SESSION
visit_pv=BL24I-MO-IOC-13:GP100
# visit=$(caget -S $ft_pv)
visit=$(echo "$(caget -S $visit_pv)" | awk '{print $NF}')
session=${visit##$visit_pv}
echo $session

if [[ -z "$session" ]]; then
    # if PV is empty print error message and exit
    echo "The visit PV has not been set, please contact beamline staff"
    exit 1
fi

export INSTRUMENT_SESSION=$session

# Get edm path from input
edm_path=$1

# Export env variable for the stages edm to work properly
export EDMDATAFILES="/dls_sw/prod/R3.14.12.3/support/motor/6-7-1dls14/motorApp/opi/edl"

# Get the directory of this script
current=$( realpath "$( dirname "$0" )" )


if [[ $NO_PROCESERV_TEST == true ]]; then
    echo "Start the blueapi sever"

    # Run script to start blueapi serve
    . $current/start_blueapi.sh
fi

echo "Set up logging configuration"
blueapi -c "${current}/blueapi_config.yaml" controller run setup_collection_logs '{"expt":"Serial Fixed"}'

# Open the edm screen for a fixed target serial collection
echo "Starting fixed target edm screen."
edm -x "${edm_path}/FT-gui/DiamondChipI24-py3v1.edl"

echo "Edm screen closed"

echo "Clean up log configuration"
blueapi -c "${current}/blueapi_config.yaml" controller run clean_up_log_config_at_end

if [[ $NO_PROCESERV_TEST == true ]]; then
    # In this case blueapi server needs to be killed.
    pgrep blueapi | xargs kill
    echo "Blueapi process killed"
fi

echo "All done, bye!"
