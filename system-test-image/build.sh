#!/bin/bash

IMAGE=mx-bluesky-st-runner
DOCKERFILE=Dockerfile

show_help() {
    echo "$(basename $0) [options...]"
cat <<END
Build and optionally push the GitHub actions runner for the mx-bluesky system tests
  --help                  This help
  --push                  Push the image to ghcr.io
  --ispyb-test-db         Build the ispyb-test-db image
END
    exit 0
}

login_to_ghcr_io() {
  podman login --get-login ghcr.io
  if [[ $? != 0 ]]; then
    echo "Not logged in to ghcr.io - please login"
    read -p "Please enter your github username:" USERNAME
    read -p "Please enter your personal access token:" PAT
    echo $PAT | podman login ghcr.io --username $USERNAME --password-stdin
  fi
  if [[ $? != 0 ]]; then
    echo "Login failed"
    exit 1
  fi
}

for option in "$@"; do
  case $option in
    --help)
      show_help
      ;;
    --push)
      PUSH=1
      shift
      ;;
    --ispyb-test-db)
      IMAGE=mx-bluesky-test-db
      DOCKERFILE=Dockerfile.ispyb-test-db
  esac
done


# Build the system test docker image
NAMESPACE=diamondlightsource
podman build -f ${DOCKERFILE} -t $IMAGE

if [[ $PUSH = 1 ]]; then
  login_to_ghcr_io
  podman push $IMAGE:latest docker://ghcr.io/$NAMESPACE/$IMAGE:latest
fi
