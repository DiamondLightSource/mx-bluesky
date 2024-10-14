#!/bin/bash

# Get the directory of this script
current=$( realpath "$( dirname "$0" )" )

# Start the blueapi worker using the config file in this module
echo "Starting the blueapi runner"
blueapi -c "${current}/blueapi_config.yaml" serve &

# Wait for blueapi to start
for i in {1..30}
do
    echo "$(date)"
    curl --head -X GET http://localhost:25565/status >/dev/null
    ret_value=$?
    if [ $ret_value -ne 0 ]; then
        sleep 1
    else
        break
    fi
done

if [ $ret_value -ne 0 ]; then
    echo "$(date) BLUEAPI Failed to start!!!!"
    exit 1
else
    echo "$(date) BLUEAPI started"
fi
