#!/bin/bash
# Entry point for the production docker image that launches the external callbacks
# as well as the main server
IN_DEV=false
CALLBACKS=false
APP_DIR=/app/mx-bluesky

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
            . /app/mx-bluesky/.venv/bin/activate
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


cd $APP_DIR
. .venv/bin/activate
uv pip list

echo "$(date) Logging to $LOG_DIR"
mkdir -p $LOG_DIR

#Add future arguments here
args=""
command="hyperion"
if [ $IN_DEV == true ]; then
  args+="--dev "
fi
CONFIG_DIR=/etc/hyperion
if [ $CALLBACKS == true ]; then
  command="hyperion-callbacks"
  args+="--stomp-config $CONFIG_DIR/blueapi_callbacks.yml"
else
  args+="--mode supervisor --client-config $CONFIG_DIR/client_config.yaml --supervisor-config $CONFIG_DIR/supervisor_config.yaml"
fi

echo "$(date) Starting $command..."
$command $args
sleep 600
