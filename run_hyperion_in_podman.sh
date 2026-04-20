#!/bin/bash

STOP=0
START=0
UP=0
IN_DEV=false

show_help() {
    echo "$(basename $0) [options...]"
cat <<END
Script for the convenience of running a container image locally using podman-compose.

  --dev                   Start a dev container bound against source folders that launches into a bash shell
  -b, --beamline=BEAMLINE Overrides the BEAMLINE environment variable with the given beamline
 
Operations
  --stop                  Used to stop a currently running instance of Hyperion. Will override any other operations
                          options
  --start                 Specify that the script should start the server
  --up                    Create the container for the service but do not start
  --restart               Specify that the script should stop and then start the server.
END
    exit 0  
}

for option in "$@"; do
    case $option in
        -b=*|--beamline=*)
            BEAMLINE="${option#*=}"
            shift
            ;;
        --stop)
            STOP=1
            ;;
        --start)
            START=1
            ;;
        --up)
            UP=1
            START=0
            ;;
        --logs)
          LOGS=1
          ;;
        --restart)
            STOP=1
            START=1
            ;;
        --dev)
            IN_DEV=true
            ;;

        --help|--info|--h)
            show_help
            ;;
        -*|--*)
            echo "Unknown option ${option}. Use --help for info on option usage."
            exit 1
            ;;
    esac
done

if [[ $START = 0 && $STOP = 0 && $UP = 0 ]]; then
  echo "One of --start, --stop, --restart or --up must be specified"
  show_help
fi

ensure_prerequisites() {
      if [[ -z $VIRTUAL_ENV ]]; then
        echo "Activating virtual environment"
        . $RELATIVE_SCRIPT_DIR/.venv/bin/activate
      fi
      TYPE=$(type -t podman-compose)  
      if [[ $TYPE != file ]]; then
        pip install podman-compose
      fi
}

kill_active_apps () {
    echo "Killing active instances of hyperion and hyperion-callbacks..."
    podman compose -f ${COMPOSE_YAML} stop ${SERVICE}
    echo "done."
}

check_user () {
    if [[ $HOSTNAME != "${BEAMLINE}-control.diamond.ac.uk" || $USER != "gda2" ]]; then
        echo "Must be run from beamline control machine as gda2"
        echo "Current host is $HOSTNAME and user is $USER"
        exit 1
    fi
}

RELATIVE_SCRIPT_DIR=$( dirname -- "$0"; )

COMPOSE_YAML=${RELATIVE_SCRIPT_DIR}/utility_scripts/docker/${BEAMLINE}-compose.yml
EXTRA_ARGS=""

if [[ -z "${BEAMLINE}" ]]; then
    echo "BEAMLINE parameter not set."
    echo "If you would like to run on a dev machine set the option -b, --beamline=BEAMLNE to set it manually"
    exit 1
fi

if [[ $IN_DEV == false ]]; then
  SERVICE=hyperion
else
  if [[ $UP == 1 ]]; then
    echo "--up cannot be used with --dev"
    exit 1
  fi
  SERVICE=hyperion-dev
fi

ensure_prerequisites

if [[ $LOGS == 1 ]]; then
  podman compose -f ${COMPOSE_YAML} logs ${SERVICE}
  exit 0 
fi

if [[ $STOP == 1 ]]; then
    if [[ $IN_DEV == false ]]; then
        check_user
    fi
    kill_active_apps

    echo "Hyperion stopped"
fi

if [[ $UP == 1 ]]; then
  podman compose -f ${COMPOSE_YAML} down --remove-orphans
  podman compose -f ${COMPOSE_YAML} up --no-start --no-build ${SERVICE}
fi

if [[ $START == 1 ]]; then
    if [ $IN_DEV == false ]; then
        check_user
    fi

    kill_active_apps

    if [[ $IN_DEV == true ]]; then
      echo "Starting with podman compose -f ${COMPOSE_YAML} run -v ${HOME}/.zocalo:/root/.zocalo ${SERVICE}"
      podman compose -f ${COMPOSE_YAML} run -v ${HOME}/.zocalo:/root/.zocalo ${SERVICE}
    else
      echo "Starting with podman compose -f ${COMPOSE_YAML} start ${SERVICE}"
      podman compose -f ${COMPOSE_YAML} start ${SERVICE}
    fi
fi
