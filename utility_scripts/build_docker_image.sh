#!/bin/bash
set -e
# builds the docker image
BUILD=1
PUSH=1
PODMAN_FLAGS=""
for option in "$@"; do
    case $option in
        --no-build)
            BUILD=0
            shift
            ;;
        --no-push)
            PUSH=0
            shift
            ;;
        --no-cache)
            PODMAN_FLAGS+=" --no-cache"
            shift
            ;;
        --help|--info|--h)
            CMD=`basename $0`
            echo "$CMD [options]"
            echo "Builds and/or pushes the docker container image to the repository"
            echo "  --help                  This help"
            echo "  --no-build              Do not build the image"
            echo "  --no-push               Do not push the image"
            echo "  --no-cache              Don't use the cache when building the image."
            exit 0
            ;;
        -*|--*)
            echo "Unknown option ${option}. Use --help for info on option usage."
            exit 1
            ;;
    esac
done

PROJECTDIR=`dirname $0`/..
IMAGE=mx-bluesky

if ! git diff --cached --quiet; then
  echo "Cannot build image from unclean workspace"
  exit 1
fi


if [[ $BUILD == 1 ]]; then
  echo "Building initial image"
  LATEST_TAG=$IMAGE:latest
  TMPDIR=/tmp podman build \
    $PODMAN_FLAGS \
    -f $PROJECTDIR/Dockerfile.release \
    --tag $LATEST_TAG \
    $PROJECTDIR
  # Now extract the version from the built image and then rebuild with the label
  IMAGE_VERSION=$(podman run --rm --entrypoint=hyperion $LATEST_TAG -c "--version" | \
   sed -e 's/[^a-zA-Z0-9 ._-]/_/g')
  TAG=$IMAGE:$IMAGE_VERSION
  echo "Labelling image with version $IMAGE_VERSION, tagging with tags $TAG $LATEST_TAG"
  TMPDIR=/tmp podman build \
    -f $PROJECTDIR/Dockerfile.release \
    --tag $TAG \
    --tag $LATEST_TAG \
    --label "version=$IMAGE_VERSION" \
    $PROJECTDIR  
fi

if [[ $PUSH == 1 ]]; then
  NAMESPACE=$(podman login --get-login ghcr.io | tr '[:upper:]' '[:lower:]')
  if [[ $? != 0 ]]; then
    echo "Not logged in to ghcr.io"
    exit 1
  fi
  echo "Pushing to ghcr.io/$NAMESPACE/$IMAGE:latest ..."
  podman push $IMAGE:latest docker://ghcr.io/$NAMESPACE/$IMAGE:latest
  podman push $IMAGE:latest docker://ghcr.io/$NAMESPACE/$IMAGE:$IMAGE_VERSION
fi
