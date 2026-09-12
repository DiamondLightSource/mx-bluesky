#!/bin/bash
set -eo pipefail
# Script for building development docker images
BUILD=1
PUSH=0
BUILD_UNCLEAN=0
BUILD_HELM=0
PODMAN_FLAGS=""
for option in "$@"; do
    case $option in
        --no-build)
            BUILD=0
            shift
            ;;
        --push)
            PUSH=1
            shift
            ;;
        --no-cache)
            PODMAN_FLAGS+=" --no-cache"
            shift
            ;;
        --unclean)
            BUILD_UNCLEAN=1
            shift
            ;;
        --helm)
          BUILD_HELM=1
          shift
          ;;
        --help|--info|--h)
            CMD=`basename $0`
            echo "$CMD [options]"
            echo "Builds a development hyperion docker image and optionally pushes the docker container image to the repository"
            echo "  --help                  This help"
            echo "  --no-build              Do not build the image"
            echo "  --push                  Push the image"
            echo "  --no-cache              Don't use the cache when building the image."
            echo "  --unclean               Build with an unclean workspace"
            echo "  --helm                  Build (and optionally push) the helm chart"
            exit 0
            ;;
        -*|--*)
            echo "Unknown option ${option}. Use --help for info on option usage."
            exit 1
            ;;
    esac
done

PROJECTDIR=`dirname $0`/..
IMAGE=hyperion

function extract_version() {
  LATEST_VERSION=$(git tag | sed -E -n 's/^v?([[:digit:]]+\.[[:digit:]]+\.[[:digit:]]+)$/\1/p' | sort -V -r | head -1)
  GIT_HASH=$(git rev-parse --short HEAD)
  echo $LATEST_VERSION-g$GIT_HASH
}

if [[ $BUILD_UNCLEAN == 0 ]]; then
  if ! git diff --cached --quiet; then
    echo "Cannot build image from unclean workspace"
    exit 1
  fi
fi

export BIGFILES_TMPDIR=/scratch/tmp
export TMPDIR=/tmp

if [[ $BUILD == 1 ]]; then
  echo "Building initial image"
  IMAGE_VERSION=$(extract_version)
  MX_BLUESKY_VERSION=${IMAGE_VERSION/-/+}
  LATEST_TAG=$IMAGE:dev
  if [[ $BUILD_HELM == 0 ]]; then
    podman build \
      $PODMAN_FLAGS \
      --build-arg SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MX_BLUESKY=$MX_BLUESKY_VERSION \
      -f $PROJECTDIR/Dockerfile.hyperion \
      --tag $LATEST_TAG \
      --tag $IMAGE:$IMAGE_VERSION \
      $PROJECTDIR
    else
      helm dependencies update helm/$IMAGE
      helm package helm/$IMAGE --version ${IMAGE_VERSION} --app-version ${IMAGE_VERSION} -d /tmp/
    fi
fi

if [[ $PUSH == 1 ]]; then
  NAMESPACE=$(podman login --get-login ghcr.io | tr '[:upper:]' '[:lower:]')
  if [[ $BUILD_HELM == 0 ]]; then
    if [[ $? != 0 ]]; then
      echo "Not logged in to ghcr.io"
      exit 1
    fi
    echo "Pushing to ghcr.io/$NAMESPACE/$IMAGE:dev ..."
    podman push $IMAGE:dev docker://ghcr.io/$NAMESPACE/$IMAGE:dev
    podman push $IMAGE:dev docker://ghcr.io/$NAMESPACE/$IMAGE:$IMAGE_VERSION
  else
    helm push /tmp/hyperion-${IMAGE_VERSION}.tgz oci://ghcr.io/$NAMESPACE/charts
  fi
fi
