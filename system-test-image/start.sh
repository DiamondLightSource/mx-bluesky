#!/bin/bash
echo "Fetching token"
REG_TOKEN=$(curl -X POST \
  -H "Authorization: token ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/DiamondLightSource/mx-bluesky/actions/runners/registration-token | \
  jq .token --raw-output)

./config.sh  \
  --unattended \
  --url https://github.com/DiamondLightSource/mx-bluesky \
  --token ${REG_TOKEN} \
  --labels system-tests \
  --name "mx-bluesky-system-test" && \
  echo "Registered successfully"

cleanup() {
  echo "Removing runner.."
  ./config.sh remove --token ${TOKEN}
}

trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

./run.sh & wait $!
