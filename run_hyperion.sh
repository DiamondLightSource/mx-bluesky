#!/bin/bash
# This is invoked by hyperion_restart() in GDA, but can also be used to run hyperion 
# locally from a dev environment

STOP=0
START=1
VERBOSE_EVENT_LOGGING=false
IN_DEV=false

for option in "$@"; do
    case $option in
        -b=*|--beamline=*)
            BEAMLINE="${option#*=}"
            shift
            ;;
        --stop)
            STOP=1
            ;;
        --no-start)
            START=0
            ;;
        --dev)
            IN_DEV=true
            ;;
        --verbose-event-logging)
            VERBOSE_EVENT_LOGGING=true
            ;;

        --help|--info|--h)
            source .venv/bin/activate
            echo "`basename $0` [options]"
            cat <<END

This script must be run from a beamline control machine unless --dev is specified.

Options:
  -b, --beamline=BEAMLINE Overrides the BEAMLINE environment variable with the given beamline
  --stop                  Used to stop a currently running instance of Hyperion. Will override any other operations
                          options.
  --no-start              Used to specify that the script should be run without starting the server.
  --skip-startup-connection
                          Do not connect to devices at startup
  --dev                   Enable dev mode to run from a local workspace on a development machine.
                          Implied if BEAMLINE is not set.
  --verbose-event-logging Enable verbose event logging
  --help                  This help

By default this script will start an Hyperion server unless the --no-start flag is specified.
END
            exit 0
            ;;
        -*|--*)
            echo "Unknown option ${option}. Use --help for info on option usage."
            exit 1
            ;;
    esac
done

kill_active_apps () {
    echo "Killing active instances of hyperion and hyperion-callbacks..."
    pkill -e -f "python.*hyperion"
    pkill -e -f "SCREEN.*hyperion"
    echo "done."
}

check_user () {
    if [[ $HOSTNAME != "${BEAMLINE}-control.diamond.ac.uk" || $USER != "gda2" ]]; then
        echo "Must be run from beamline control machine as gda2"
        echo "Current host is $HOSTNAME and user is $USER"
        exit 1
    fi
}

if [ -z "${BEAMLINE}" ]; then
    echo "BEAMLINE parameter not set, assuming running on a dev machine."
    echo "If you would like to run not in dev use the option -b, --beamline=BEAMLNE to set it manually"
    IN_DEV=true
fi

if [[ $STOP == 1 ]]; then
    if [ $IN_DEV == false ]; then
        check_user
    fi
    kill_active_apps

    echo "Hyperion stopped"
    exit 0
fi

if [[ $START == 1 ]]; then
    RELATIVE_SCRIPT_DIR=$( dirname -- "$0"; )
    if [ $IN_DEV == false ]; then
        check_user
        ISPYB_CONFIG_PATH="/dls_sw/dasc/mariadb/credentials/ispyb-hyperion-${BEAMLINE}.cfg"
    else
        ISPYB_CONFIG_PATH="$RELATIVE_SCRIPT_DIR/tests/test_data/ispyb_test_credentials.cfg"
        ZOCALO_CONFIG="$RELATIVE_SCRIPT_DIR/tests/test_data/zocalo-test-configuration.yaml"
        export ZOCALO_CONFIG
    fi
    export ISPYB_CONFIG_PATH

    kill_active_apps

    module unload controls_dev
    module load dials

    cd ${RELATIVE_SCRIPT_DIR}

    if [ -z "$LOG_DIR" ]; then
        if [ $IN_DEV == true ]; then
            LOG_DIR=$RELATIVE_SCRIPT_DIR/tmp/dev
        else
            LOG_DIR=/dls_sw/$BEAMLINE/logs/bluesky
        fi
    fi
    echo "$(date) Logging to $LOG_DIR"
    export LOG_DIR
    mkdir -p $LOG_DIR
    start_log_path=$LOG_DIR/start_log.log
    callback_start_log_path=$LOG_DIR/callback_start_log.log

    source .venv/bin/activate

    #Add future arguments here
    declare -A h_only_args=( ["VERBOSE_EVENT_LOGGING"]="$VERBOSE_EVENT_LOGGING" )
    declare -A h_only_arg_strings=( ["VERBOSE_EVENT_LOGGING"]="--verbose-event-logging" )

    declare -A h_and_cb_args=( ["IN_DEV"]="$IN_DEV" )
    declare -A h_and_cb_arg_strings=( ["IN_DEV"]="--dev" )

    h_commands=()
    for i in "${!h_only_args[@]}"
    do
        if [ "${h_only_args[$i]}" != false ]; then 
            h_commands+="${h_only_arg_strings[$i]} ";
        fi;
    done
    cb_commands=()
    for i in "${!h_and_cb_args[@]}"
    do
        if [ "${h_and_cb_args[$i]}" != false ]; then 
            h_commands+="${h_and_cb_arg_strings[$i]} ";
            cb_commands+="${h_and_cb_arg_strings[$i]} ";
        fi;
    done

    unset PYEPICS_LIBCA
    echo "Starting hyperion with hyperion $h_commands, start_log is $start_log_path"
    hyperion `echo $h_commands;`>$start_log_path  2>&1 &
    echo "Starting hyperion-callbacks with hyperion-callbacks $cb_commands, start_log is $callback_start_log_path"
    hyperion-callbacks `echo $cb_commands;`>$callback_start_log_path 2>&1 &
    echo "$(date) Waiting for Hyperion to start"

    for i in {1..30}
    do
        echo "$(date)"
        curl --head -X GET http://localhost:5005/status >/dev/null
        ret_value=$?
        if [ $ret_value -ne 0 ]; then
            sleep 1
        else
            break
        fi
    done

    if [ $ret_value -ne 0 ]; then
        echo "$(date) Hyperion Failed to start!!!!"
        exit 1
    else
        echo "$(date) Hyperion started"
    fi
fi

sleep 1
