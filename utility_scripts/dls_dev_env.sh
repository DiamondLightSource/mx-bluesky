#!/bin/bash

# Check we're in the right place (assuming the location of this script in the repo)

# Get the directory where the script is located
script_dir=$(dirname "$(readlink -f "$0")")

# Get the current working directory
current_dir=$(pwd)

# Get the directory up from the script's location
two_levels_up=$(dirname "$script_dir")

if ! git diff --quiet pyproject.toml; then
    echo "Error: pyproject.toml has uncommitted changes. Commit or stash changes to this file before running this script again."
    exit 1
fi

# controls_dev sets pip up to look at a local pypi server, which is incomplete
module unload controls_dev 

if [ -d "./.venv" ]
then
rm -rf .venv
fi

module load python/3.11 && module load uv
uv sync --editable --group dev
source .venv/bin/activate
pre-commit install
module unload python && module unload uv

# Ensure we use a local version of dodal
if [ ! -d "../dodal" ]; then
  git clone git@github.com:DiamondLightSource/dodal.git ../dodal
fi

uv pip install -e ../dodal/

# get dlstbx into our env
ln -s /dls_sw/apps/dials/latest/latest/modules/dlstbx/src/dlstbx/ .venv/lib/python3.11/site-packages/dlstbx

pytest tests/unit_tests/
