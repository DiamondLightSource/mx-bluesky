#!/bin/bash
# Installs helm package to kubernetes
LOGIN=true

for option in "$@"; do
    case $option in
        -b=*|--beamline=*)
            BEAMLINE="${option#*=}"
            shift
            ;;
        --dev)
            DEV=true
            shift
            ;;
        --checkout-to-prod)
            CHECKOUT=true
            shift
            ;;
        --repository=*)
            REPOSITORY="${option#*=}"
            shift
            ;;
        --appVersion=*)
            APP_VERSION="${option#*=}"
            shift
            ;;
        --no-login)
            LOGIN=false
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|--info|--h)
            CMD=`basename $0`
            echo "$CMD [options] <release> <app_name>"
            cat <<EOM
Deploys a mx_bluesky app to kubernetes

Important!
If you do not specify --checkout-to-prod YOU MUST run this from the mx_bluesky directory that will be bind-mounted to
the container, NOT the directory that you built the container image from.

  --help                  This help
  --appVersion=version    Version of the image to fetch from the repository otherwise it is deduced
                          from the setuptools_scm. Must be in the format x.y.z
  -b, --beamline=BEAMLINE Overrides the BEAMLINE environment variable with the given beamline
  --checkout-to-prod      Checkout source folders to the production folder using deploy_mx_bluesky.py
  --dev                   Install to a development kubernetes cluster (assumes project checked out under /home)
                          (default cluster is argus in user namespace)
  --dry-run               Do everything but don't do the final deploy to k8s 
  --no-login              Do not attempt to log in to kubernetes instead use the current namespace and cluster
  --repository=REPOSITORY Override the repository to fetch the image from
EOM
            exit 0
            ;;
        -*|--*)
            echo "Unknown option ${option}. Use --help for info on option usage."
            exit 1
            ;;
    esac
done

if [[ -z $BEAMLINE ]]; then
  echo "BEAMLINE not set and -b not specified"
  exit 1
fi

RELEASE=$1

if [[ -z $RELEASE ]]; then
  echo "Release must be specified"
  exit 1
fi

APP_NAME=$2

if [[ -z $APP_NAME ]]; then
  echo "App name must be specified, currently supporting hyperion and redis-to-murko"
  exit 1
else
  if [[ "$APP_NAME" != "hyperion" && "$APP_NAME" != "redis-to-murko" ]]; then
    echo "Invalid app name specified. Please provide either 'hyperion' or 'redis-to-murko'."
    exit 1
  fi
fi


HELM_OPTIONS=""
PROJECTDIR=$(readlink -e $(dirname $0)/../..)
TOP_HELMCHART_DIR=${PROJECTDIR}/helmcharts
HELMCHART_DIR=${TOP_HELMCHART_DIR}/${APP_NAME}

if [[ -n $DEV ]]; then
  if [[ -n $CHECKOUT ]]; then
    echo "Cannot specify both --dev and --checkout-to-prod"
    exit 1
  fi
  CHECKED_OUT_VERSION=$(git describe --tag)
else
  if [[ -z ${VIRTUAL_ENV#${PROJECTDIR}} ]]; then
    echo "Virtual env not activated, activating"
    . $PROJECTDIR/.venv/bin/activate
  fi

  # First extract the version and location that will be deployed
  DEPLOY_MX_BLUESKY="python $PROJECTDIR/utility_scripts/deploy/deploy_mx_bluesky.py"
  MX_BLUESKY_BASE=$($DEPLOY_MX_BLUESKY --print-release-dir $BEAMLINE)

  if [[ -n $CHECKOUT ]]; then
    echo "Running deploy_mx_bluesky.py to deploy to production folder..."
    $DEPLOY_MX_BLUESKY --kubernetes $BEAMLINE
    if [[ $? != 0 ]]; then
      echo "Deployment failed, aborting."
      exit 1
    fi
  fi

  NEW_PROJECTDIR=$MX_BLUESKY_BASE/mx-bluesky
  echo "Changing directory to $NEW_PROJECTDIR..."
  cd $NEW_PROJECTDIR
  PROJECTDIR=$NEW_PROJECTDIR
  MX_BLUESKY_BASENAME=$(basename $MX_BLUESKY_BASE)
  CHECKED_OUT_VERSION=${MX_BLUESKY_BASENAME#mx-bluesky_v}
fi


if [[ $LOGIN = true ]]; then
  if [[ -n $DEV ]]; then
    CLUSTER=argus
    NAMESPACE=$(whoami)
  else
    CLUSTER=k8s-$BEAMLINE
    NAMESPACE=$BEAMLINE-beamline
  fi
fi

ensure_version_py() {
  # We require the _version.py to be created, this needs a minimal virtual environment
  if [[ ! -d $PROJECTDIR/.venv ]]; then
    echo "Creating _version.py"
    echo "Virtual environment not found - creating"
    module load python/3.11
    python -m venv $PROJECTDIR/.venv
    . $PROJECTDIR/.venv/bin/activate
  fi
  pip install setuptools_scm
}

app_version() {
  . $PROJECTDIR/.venv/bin/activate
  python -m setuptools_scm --force-write-version-files | sed -e 's/[^a-zA-Z0-9._-]/_/g'
}

if [[ -n $REPOSITORY ]]; then
  HELM_OPTIONS+="--set application.imageRepository=$REPOSITORY "
fi

ensure_version_py
if [[ -z $APP_VERSION ]]; then
  APP_VERSION=$(app_version)
fi

echo "Checked out version that will be bind-mounted in $PROJECTDIR is $CHECKED_OUT_VERSION"
echo "Container image version that will be pulled is $APP_VERSION"

if [[ $APP_VERSION != $CHECKED_OUT_VERSION ]]; then
  echo "*****************************************************************"
  echo "WARNING: Checked out version and container image versions differ!"
  echo "*****************************************************************"
fi

if [[ -n $DEV ]]; then
  GID=`id -g`
  SUPPLEMENTAL_GIDS=37904
  HELM_OPTIONS+="--set \
application.dev=true,\
application.runAsUser=$EUID,\
application.runAsGroup=$GID,\
application.supplementalGroups=[$SUPPLEMENTAL_GIDS],\
application.logDir=$PROJECTDIR/tmp,\
application.dataDir=$PROJECTDIR/tmp/data,\
application.externalHostname=test-$APP_NAME.diamond.ac.uk "
  mkdir -p $PROJECTDIR/tmp/data
  DEPLOYMENT_DIR=$PROJECTDIR
else
  DEPLOYMENT_DIR=/dls_sw/$BEAMLINE/software/bluesky/mx-bluesky_v${APP_VERSION}/mx-bluesky
fi

HELM_OPTIONS+="--set application.appVersion=v$APP_VERSION,\
application.projectDir=$DEPLOYMENT_DIR,\
dodal.projectDir=$DEPLOYMENT_DIR/../dodal "

module load helm

helm package $HELMCHART_DIR --app-version $APP_VERSION
# Helm package generates a file suffixed with the chart version
if [[ $LOGIN = true ]]; then
  module load $CLUSTER
  kubectl config set-context --current --namespace=$NAMESPACE
fi
if [[ -z $DRY_RUN ]]; then
  helm upgrade --install $HELM_OPTIONS $RELEASE $APP_NAME-0.0.1.tgz
fi
