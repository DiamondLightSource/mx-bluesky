#!/bin/bash
# This script is run in the initContainer before the main hyperion pod is launched to initialise the scratch area
# if not already present
SCRATCH_ROOT=/scratch
APP_ROOT=/app

if [ ! -d $SCRATCH_ROOT/mx-bluesky/.git ]; then
  CURRENT_BRANCH=$(git --git-dir=$APP_ROOT/mx-bluesky/.git rev-parse --abbrev-ref HEAD)
  git clone /app/mx-bluesky/.git $SCRATCH_ROOT/mx-bluesky
  cd $SCRATCH_ROOT/mx-bluesky
  git checkout $CURRENT_BRANCH
fi
