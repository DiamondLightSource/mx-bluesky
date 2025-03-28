#!/bin/bash

STOP=0
START=1
SKIP_STARTUP_CONNECTION=false
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
        --skip-startup-connection)
            SKIP_STARTUP_CONNECTION=true
            ;;
        --dev)
            IN_DEV=true
            ;;
        --verbose-event-logging)
            VERBOSE_EVENT_LOGGING=true
            ;;

        --help|--info|--h)
        
        #Combine help from here and help from mx_bluesky.hyperion
            source .venv/bin/activate
            python -m hyperion --help
            echo "  -b, --beamline=BEAMLINE Overrides the BEAMLINE environment variable with the given beamline"
            echo " "
            echo "Operations"
            echo "  --stop                  Used to stop a currently running instance of Hyperion. Will override any other operations"
            echo "                          options"
            echo "  --no-start              Used to specify that the script should be run without starting the server."
            echo " "
            echo "By default this script will start an Hyperion server unless the --no-start flag is specified."
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
    if [ $IN_DEV == false ]; then
        check_user

        ISPYB_CONFIG_PATH="/dls_sw/dasc/mariadb/credentials/ispyb-hyperion-${BEAMLINE}.cfg"
        export ISPYB_CONFIG_PATH

    fi

    kill_active_apps

    module unload controls_dev
    module load dials

    RELATIVE_SCRIPT_DIR=$( dirname -- "$0"; )
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
    declare -A h_only_args=(        ["SKIP_STARTUP_CONNECTION"]="$SKIP_STARTUP_CONNECTION"
                                    ["VERBOSE_EVENT_LOGGING"]="$VERBOSE_EVENT_LOGGING" )
    declare -A h_only_arg_strings=( ["SKIP_STARTUP_CONNECTION"]="--skip-startup-connection"
                                    ["VERBOSE_EVENT_LOGGING"]="--verbose-event-logging" )

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
    hyperion `echo $h_commands;`>$start_log_path  2>&1 &
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
