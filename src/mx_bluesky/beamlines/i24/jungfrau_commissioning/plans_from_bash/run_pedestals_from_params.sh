#!/bin/bash

source ../../../../../../.venv/bin/activate

read -p "Are you sure you want to run a pedestal scan? Press Y to continue or N to cancel: " confirm

# Check input
case "$confirm" in
    [Yy])
        echo "Running pedestals..."
        python pedestals.py 2>&1
        ;;
    *)
        echo "Cancelled by user."
        ;;
esac
