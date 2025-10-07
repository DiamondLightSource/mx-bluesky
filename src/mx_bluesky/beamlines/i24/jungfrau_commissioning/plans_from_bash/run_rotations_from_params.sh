#!/bin/bash

source ../../../../../../.venv/bin/activate

read -p "Are you sure you want to run a rotation scan? Press Y to continue or N to cancel: " confirm

# Check input
case "$confirm" in
    [Yy])
        echo "Running rotations..."
        python rotations.py 2>&1
        ;;
    *)
        echo "Cancelled by user."
        ;;
esac
