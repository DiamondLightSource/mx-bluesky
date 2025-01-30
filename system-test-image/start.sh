#!/bin/bash
# This is run inside the system tests container image
REPO=https://github.com/DiamondLightSource/mx-bluesky.git
BRANCH=main

show_help() {
    echo "$(basename $0) [options...]"
cat <<END
Run the mx-bluesky system tests
  --help                  This help
  --repo=<repo_url>       Specify the URL of the repo to fetch.
                          Default is ${REPO}
  --branch=<branch>       Specify the branch to check out
                          Default is ${BRANCH}
END
    exit 0
}

for option in "$@"; do
  case $option in
    --help)
      show_help
      ;;
    --repo=*)
      REPO="${option#*=}"
      shift
      ;;
    --branch=*)
      BRANCH="${option#*=}"
      shift
      ;;
  esac
done

set -e
git clone ${REPO}
cd mx-bluesky
git checkout ${BRANCH}
pip install -e .[dev]
tox -e systemtests
