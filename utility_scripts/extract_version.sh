#!/bin/bash

LATEST_VERSION=$(git tag | sed -E -n 's/^v?([[:digit:]]+\.[[:digit:]]+\.[[:digit:]]+)$/\1/p' | sort -V -r | head -1)
GIT_HASH=$(git rev-parse --short HEAD)
echo $LATEST_VERSION-g$GIT_HASH
