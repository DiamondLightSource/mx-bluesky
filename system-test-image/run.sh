#!/bin/bash
# Run the system test image locally
# Set TOKEN to your API token before running
# e.g. TOKEN=<my token> ./run.sh
# to remove the runner
# ./config remove
podman run --secret actionsRunnerToken,type=env,target=TOKEN \
  -i mx-bluesky-st:latest
  
