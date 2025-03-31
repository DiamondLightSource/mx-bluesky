#!/bin/bash

# Set visit directory for current experiment type from values stored in a file
filename="/dls_sw/i24/etc/ssx_current_visit.txt"

display_help_msg() {
    usage="./set_visit_directory.sh [expt_type]"
    echo "USAGE: $usage"
    echo "This script sets the visit directory for a serial crystallography experiment on I24."
    echo "The current visit directory is saved in: $filename. Please modify this file to set a new visit."
    echo "WARNING. The experiment type is set by default to fixed-target." 
    echo "To set the directory for an extruder experiment please pass extruder as a command line argument." 
}

case "$1" in
    -h | --help)
        display_help_msg
        exit 0
        ;;
esac


if [[ ! -f "$filename" ]]; then
    echo "The file $filename does not exist. Impossible to set the visit directory."
    exit 1
fi

echo "Reading visit from file: $filename"

visit=$(sed -n '1p' $filename)
expt_type=${1:-FT}

# Append a / to the visit if missing to avoid filepaths issues later on
if [[ "${visit: -1}" != "/" ]]; then
    visit="${visit}/"
fi

ex_pv=BL24I-MO-IOC-13:GP1
ft_pv=ME14E-MO-IOC-01:GP100

shopt -s nocasematch

if [[ $expt_type == "FT" ]] || [[ $expt_type == "fixed-target" ]]
then
    echo "Setting visit PV for serial fixed-target collection."
    caput  $ft_pv $visit
    echo "Visit set to: $visit."
elif [[ $expt_type == "EX" ]] || [[ $expt_type == "extruder" ]]
then
    echo "Setting visit PV for serial extruder collection."
    caput  $ex_pv $visit
    echo "Visit set to: $visit"
else
    echo -e "Unknown experiment type, visit PV not set. \nValid experiment values: fixed-target, extruder."
    exit 1
fi
