#!/bin/bash
./config.sh  --url https://github.com/DiamondLightSource/mx-bluesky \
  --name "mx-bluesky-system-test" \
  --token ${TOKEN} \
  --unattended

cleanup() {
  echo "Removing runner.."
  ./config.sh remove --token ${TOKEN}
}

trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

./run.sh & wait $!
