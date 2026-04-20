#!/bin/bash

# Deploy EDM screens for serial crystallography
# Make a copy of them in edm/ and replace paths

current=$( realpath "$( dirname "$0" )" )
base=$(dirname $(dirname $current))

edm_build="$base/edm_serial"

echo "EDM screens for ssx will be saved in: $edm_build"

if [ -d $edm_build ]; then
    rm -rf $edm_build
fi

mkdir -p $edm_build

edm_placeholder="EDM_LOCATION"
ex_edm="$edm_build/EX-gui"
ft_edm="$edm_build/FT-gui"

mkdir $ex_edm
mkdir $ft_edm

scripts_placeholder="SCRIPTS_LOCATION"
scripts_loc="$base/src/mx_bluesky/beamlines/i24/serial"

# Add blueapi configuration file to get stomp
# See https://github.com/DiamondLightSource/blueapi/issues/485
config_placeholder="CONFIG_LOCATION"
config_loc="$scripts_loc/blueapi_config.yaml"

# Copy extruder
cp $scripts_loc/extruder/EX-gui-edm/*.edl $ex_edm
# Copy fixed target
cp $scripts_loc/fixed_target/FT-gui-edm/*.edl $ft_edm
# Different places because of edm with common name from microdrop alignment. Might change once checked.

# Fix both edm and scripts paths
echo "Setting up screen for extruder"
for filename in $ex_edm/*.edl; do
    sed -i "s+${edm_placeholder}+${ex_edm}+g" $filename     # Fix edm paths
    sed -i "s+${config_placeholder}+${config_loc}+g" $filename   # Fix config paths
done
echo "Setting up screens for fixed target"
for filename in $ft_edm/*.edl; do
    sed -i "s+${edm_placeholder}+${ft_edm}+g" $filename     # Fix edm paths
    sed -i "s+${config_placeholder}+${config_loc}+g" $filename   # Fix config paths
    sed -i "s+${scripts_placeholder}+${scripts_loc}+g" $filename  # Fix script location - needed for viewer
done

echo "EDM screen set up completed."
