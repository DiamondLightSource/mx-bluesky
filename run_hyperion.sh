#!/bin/bash
# This is invoked by hyperion_restart() in GDA, but can also be used to run hyperion 
# locally from a dev environment

STOP=0
START=1
IN_DEV=false
MODE=gda

CONFIG_DIR=`dirname $0`/src/mx_bluesky/hyperion
BLUEAPI_CONFIG=$CONFIG_DIR/blueapi_config.yaml
SUPERVISOR_CONFIG=$CONFIG_DIR/supervisor/supervisor_config.yaml
CLIENT_CONFIG=$CONFIG_DIR/supervisor/client_config.yaml
DO_CALLBACKS=1
HEALTHCHECK_PORT=5005
CALLBACK_WATCHDOG_PORT=5005

for option in "$@"; do
    case $option in
        -b=*|--beamline=*)
            BEAMLINE="${option#*=}"
            export BEAMLINE
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
            BLUEAPI_CONFIG=$CONFIG_DIR/blueapi_dev_config.yaml
            SUPERVISOR_CONFIG=$CONFIG_DIR/supervisor/supervisor_dev_config.yaml
            ;;
        --udc)
            MODE=udc
            ;;
        --blueapi)
            MODE=blueapi
            CALLBACK_WATCHDOG_PORT=5006
            ;;
        --supervisor)
            MODE=supervisor
            DO_CALLBACKS=0
            HEALTHCHECK_PORT=5006
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
  --dev                   Enable dev mode to run from a local workspace on a development machine.
  --udc                   Start hyperion in UDC mode instead of taking commands from GDA
  --blueapi               Start hyperion in blueapi mode instead of taking commands from GDA
  --supervisor            Start hyperion in supervisor mode, taking commands from Agamemnon and feeding them to
                          an instance running in blueapi mode.
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
    if [ $MODE = "supervisor" ]; then
      # supervisor mode kills only supervisor
      echo "Killing active instances of hyperion supervisor..."
      pkill -e -f "mx-bluesky/.venv/bin/python .*--mode supervisor"
    else
      echo "Killing active instances of hyperion-blueapi"
      pkill -e -f "python .*mx-bluesky/.venv/bin/blueapi .*serve"
      echo "Killing vanilla hyperion instances"
      pkill -e -f "mx-bluesky/.venv/bin/python .*--mode (gda|udc)"
      echo "Killing hyperion-callbacks"
      pkill -e -f "mx-bluesky/.venv/bin/python .*hyperion-callbacks"
    fi
}

check_user () {
    if [[ $HOSTNAME != "${BEAMLINE}-control.diamond.ac.uk" || $USER != "gda2" ]]; then
        echo "Must be run from beamline control machine as gda2"
        echo "Current host is $HOSTNAME and user is $USER"
        exit 1
    fi
}

if [ -z "${BEAMLINE}" ]; then
    echo "BEAMLINE environment variable is not set and the --beamline parameter is not specified."
    echo "Please set the option -b, --beamline=BEAMLINE to set it manually"
    exit 1
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
        ISPYB_CONFIG_PATH="$RELATIVE_SCRIPT_DIR/tests/test_data/ispyb-test-credentials.cfg"
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
    mkdir -p "$LOG_DIR"
    if [ $MODE = "supervisor" ]; then
      start_log_path=$LOG_DIR/supervisor_start_log.log
    else
      start_log_path=$LOG_DIR/start_log.log
    fi
    callback_start_log_path=$LOG_DIR/callback_start_log.log

    source .venv/bin/activate

    declare -A h_and_cb_args=( ["IN_DEV"]="$IN_DEV" )
    declare -A h_and_cb_arg_strings=( ["IN_DEV"]="--dev" )

    h_commands="--mode $MODE "
    cb_commands="--watchdog-port $CALLBACK_WATCHDOG_PORT "
    if [ $MODE = "supervisor" ]; then
      h_commands+="--client-config ${CLIENT_CONFIG} --supervisor-config ${SUPERVISOR_CONFIG} "
    fi
    for i in "${!h_and_cb_args[@]}"
    do
        if [ "${h_and_cb_args[$i]}" != false ]; then 
            h_commands+="${h_and_cb_arg_strings[$i]} ";
            cb_commands+="${h_and_cb_arg_strings[$i]} ";
        fi;
    done

    unset PYEPICS_LIBCA
    if [ $MODE = "blueapi" ]; then 
      echo "Starting hyperion in blueapi mode, start log is $start_log_path"
      blueapi --config $BLUEAPI_CONFIG serve > $start_log_path 2>&1 &
      HEALTHCHECK_ENDPOINT="healthz"
    else
      echo "Starting hyperion in mode $MODE with hyperion $h_commands, start_log is $start_log_path"
      hyperion `echo $h_commands;`>$start_log_path  2>&1 &
      HEALTHCHECK_ENDPOINT="status"
    fi
    if [[ $DO_CALLBACKS == 1 ]]; then
      echo "Starting hyperion-callbacks with hyperion-callbacks $cb_commands, start_log is $callback_start_log_path"
      hyperion-callbacks `echo $cb_commands;`>$callback_start_log_path 2>&1 &
    fi
    echo "$(date) Waiting for Hyperion to start"

    for i in {1..30}
    do
        echo "$(date)"
        curl --head -X GET http://localhost:$HEALTHCHECK_PORT/$HEALTHCHECK_ENDPOINT >/dev/null
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
