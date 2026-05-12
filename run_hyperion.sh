#!/bin/bash
# This is invoked by hyperion_restart() in GDA, but can also be used to run hyperion 
# locally from a dev environment

STOP=0
START=1
IN_DEV=false
MODE=udc

CONFIG_DIR=`dirname $0`/src/mx_bluesky/hyperion
BLUEAPI_CONFIG=$CONFIG_DIR/blueapi_config.yaml
SUPERVISOR_CONFIG=$CONFIG_DIR/supervisor/supervisor_config.yaml
CLIENT_CONFIG=$CONFIG_DIR/supervisor/client_config.yaml
STOMP_CONFIG=$CONFIG_DIR/blueapi_config.yaml
HEALTHCHECK_PORT=5005
SUPERVISOR_HEALTHCHECK_PORT=5006
CALLBACK_WATCHDOG_PORT=5005
CALLBACK_MODE=0mq
START_HYPERION_SUPERVISOR=0
START_HYPERION_BLUEAPI=0

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
            START_HYPERION_BLUEAPI=1
            CALLBACK_WATCHDOG_PORT=5006
            ;;
        --supervisor)
            MODE=blueapi
            START_HYPERION_SUPERVISOR=1
            SUPERVISOR_HEALTHCHECK_PORT=5006
            ;;
	--stomp)
	    CALLBACK_MODE=stomp
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
  --udc                   (Re)start hyperion in UDC mode taking instructions from agamemnon in a monolithic process
  --blueapi               (Re)start hyperio-blueapi taking instructions from the supervisor
  --supervisor            (Re)start hyperion-supervisor, taking commands from Agamemnon and feeding them to
                          hyperion-blueapi.
  --stomp                 Start external callbacks in stomp mode instead of 0mq (the default)
  --help                  This help

By default this script will start an Hyperion server unless the --no-start flag is specified.
Note: --udc is exclusive with --supervisor and --blueapi.
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
    echo "Killing vanilla hyperion instances"
    pkill -e -f "\.venv/bin/python3? .*--mode (gda|udc)"
    if [[ $START_HYPERION_SUPERVISOR == 1 || $MODE = "udc" || $STOP == 1 ]]; then
      # supervisor mode kills only supervisor
      echo "Killing active instances of hyperion supervisor..."
      pkill -e -f "\.venv/bin/python3? .*--mode supervisor"
    fi
    if [[ $START_HYPERION_BLUEAPI == 1 || $MODE = "udc" || $STOP == 1 ]]; then
      echo "Killing active instances of hyperion-blueapi"
      pkill -e -f "python3? .*/\.venv/bin/blueapi .*serve"
      echo "Killing hyperion-callbacks"
      pkill -e -f "\.venv/bin/python3? .*hyperion-callbacks"
    fi
}

check_user () {
    if [[ $HOSTNAME != "${BEAMLINE}-control.diamond.ac.uk" || $USER != "gda2" ]]; then
        echo "Must be run from beamline control machine as gda2"
        echo "Current host is $HOSTNAME and user is $USER"
        exit 1
    fi
}

wait_for_healthcheck () {
    local APP=$1
    local HEALTHCHECK_PORT=$2
    local HEALTHCHECK_ENDPOINT=$3
    echo "$(date) Waiting for $APP to start"
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
        echo "$(date) $APP Failed to start!!!!"
        exit 1
    else
        echo "$(date) Hyperion started"
    fi
}

if [ -z "${BEAMLINE}" ]; then
    echo "BEAMLINE environment variable is not set and the --beamline parameter is not specified."
    echo "Please set the option -b, --beamline=BEAMLINE to set it manually"
    exit 1
fi

export CONFIG_SERVER_URL="https://${BEAMLINE}-daq-config.diamond.ac.uk"

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
        ZOCALO_CONFIG=/dls_sw/apps/zocalo/live/configuration.yaml 
    else
        ISPYB_CONFIG_PATH="$RELATIVE_SCRIPT_DIR/tests/test_data/ispyb-test-credentials.cfg"
        ZOCALO_CONFIG="$RELATIVE_SCRIPT_DIR/tests/test_data/zocalo-test-configuration.yaml"
    fi
    export ZOCALO_CONFIG
    export ISPYB_CONFIG_PATH

    kill_active_apps

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
    if [ -z "$DEBUG_LOG_DIR" ]; then
        if [ $IN_DEV = true ]; then
            DEBUG_LOG_DIR=$LOG_DIR
        else
            DEBUG_LOG_DIR=/dls/tmp/$BEAMLINE/logs/bluesky
        fi
    fi
    echo "Debug log file set to $DEBUG_LOG_DIR"
    export DEBUG_LOG_DIR
    mkdir -p "$DEBUG_LOG_DIR"
    source .venv/bin/activate

    if [[ $START_HYPERION_SUPERVISOR == 1 ]]; then
      start_log_path=$LOG_DIR/supervisor_start_log.log
    else
      start_log_path=$LOG_DIR/start_log.log
    fi
    callback_start_log_path=$LOG_DIR/callback_start_log.log

    h_commands=""
    cb_commands="--watchdog-port $CALLBACK_WATCHDOG_PORT "

    if [[ "$IN_DEV" == true ]]; then
      h_commands+="--dev "
      cb_commands+="--dev "
    fi

    if [ "${CALLBACK_MODE}" = "stomp" ]; then
       cb_commands+="--stomp-config $STOMP_CONFIG "
    fi

    unset PYEPICS_LIBCA
    if [[ $START_HYPERION_BLUEAPI == 1 ]]; then
      echo "Starting hyperion-blueapi, start log is $start_log_path"
      # start in a separate process group to avoid GDA sending it a SIGINT on
      # GDA server shutdown
      ( set -m; nohup blueapi --config $BLUEAPI_CONFIG serve > $start_log_path 2>&1 & )
      wait_for_healthcheck hyperion-blueapi $HEALTHCHECK_PORT healthz
    fi
    if [[ $START_HYPERION_SUPERVISOR == 1 ]]; then
      h_commands+="--mode supervisor --client-config ${CLIENT_CONFIG} --supervisor-config ${SUPERVISOR_CONFIG} "
      echo "Starting hyperion-supervisor with hyperion $h_commands, start_log is $start_log_path"
      hyperion `echo $h_commands;`>$start_log_path  2>&1 &
      wait_for_healthcheck hyperion-supervisor $SUPERVISOR_HEALTHCHECK_PORT status
    elif [[ $MODE = "udc" ]]; then
        h_commands+="--mode udc "
        echo "Starting hyperion udc with hyperion $h_commands, start_log is $start_log_path"
        hyperion `echo $h_commands;`>$start_log_path  2>&1 &
        wait_for_healthcheck hyperion $HEALTHCHECK_PORT status
    fi
    if [[ $START_HYPERION_BLUEAPI == 1 || $MODE = "udc" ]]; then
      echo "Starting hyperion-callbacks with hyperion-callbacks $cb_commands, start_log is $callback_start_log_path"
      hyperion-callbacks `echo $cb_commands;`>$callback_start_log_path 2>&1 &
    fi
fi

sleep 1
