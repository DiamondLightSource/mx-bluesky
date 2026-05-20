#!/bin/bash
# Entry point for the production docker image that launches the external callbacks
# as well as the main server
IN_DEV=false
CALLBACKS=false
for option in "$@"; do
    case $option in
        --dev)
            IN_DEV=true
            shift
            ;;
        --callbacks)
            CALLBACKS=true
            shift
            ;;
        --version)
            . ./.venv/bin/activate
            hyperion --version
            exit $?
            ;;
        --help|--info|--h)
            echo "Arguments:"
            echo "  --dev start in development mode without external callbacks"
            echo "  --callbacks start hyperion callbacks, otherwise start hyperion-supervisor"
            echo "  --version print the hyperion version and exit"
            exit 0
            ;;
        -*|--*)
            echo "Unknown option ${option}. Use --help for info on option usage."
            exit 1
            ;;
    esac
done

RELATIVE_SCRIPT_DIR=$( dirname -- "$0"; )
cd ${RELATIVE_SCRIPT_DIR}

. ./.venv/bin/activate

echo "$(date) Logging to $LOG_DIR"
mkdir -p $LOG_DIR
start_log_path=$LOG_DIR/start_log.log

#Add future arguments here
args=""
command="hyperion"
if [ $IN_DEV == true ]; then
  args+="--dev "
fi
if [ $CALLBACKS == true ]; then
  command="hyperion-callbacks"
fi

echo "$(date) Starting $command..."
$command $args > $start_log_path 2>&1
