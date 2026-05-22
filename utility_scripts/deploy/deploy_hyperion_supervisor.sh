#!/bin/bash
PROJECTDIR=$(dirname $0)/../..
helm package $PROJECTDIR/helm/hyperion-supervisor \
  --app-version
