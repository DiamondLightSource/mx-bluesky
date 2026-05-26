#!/bin/bash
# This script is run in the initContainer before the main hyperion pod is launched to initialise the scratch area
# if not already present
SCRATCH_ROOT=/scratch
APP_ROOT=/app

if [ ! -d $SCRATCH_ROOT/dodal/.git ]; then
  git clone /app/dodal/.git $SCRATCH_ROOT/dodal
  echo "Checking out dodal branch $DODAL_BRANCH"
  git --git-dir=$SCRATCH_ROOT/dodal checkout $DODAL_BRANCH
fi

if [ ! -d $SCRATCH_ROOT/mx-bluesky/.git ]; then
  CURRENT_BRANCH=$(git --git-dir=$APP_ROOT/mx-bluesky/.git rev-parse --abbrev-ref HEAD)
  git clone /app/mx-bluesky/.git $SCRATCH_ROOT/mx-bluesky
  ls -la $APP_ROOT/mx-bluesky/.git
  echo "Checking out $CURRENT_BRANCH... as $UID"
  ls -la $SCRATCH_ROOT/mx-bluesky/.git
  git --git-dir=$SCRATCH_ROOT/mx-bluesky checkout $CURRENT_BRANCH
fi

cd $APP_ROOT/mx-bluesky
. ./.venv/bin/activate
uv pip install -e $SCRATCH_ROOT/mx-bluesky
uv pip install -e $SCRATCH_ROOT/dodal

sleep 600
