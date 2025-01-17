#!/bin/bash
# Run the system test image locally
# configure your personal access token as a podman secret e.g.
# echo <personalAccessToken> | podman secret create actionsRunnerToken -
#
# Note: The token has a lifetime of 1 hour!
#
# to remove the runner
# ./config remove
podman run --secret actionsRunnerToken,type=env,target=TOKEN \
  -i mx-bluesky-st:latest
  
