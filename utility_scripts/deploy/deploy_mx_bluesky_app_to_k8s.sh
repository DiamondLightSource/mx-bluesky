#!/bin/bash
# Installs helm package to kubernetes
LOGIN=true
LINT=false
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
        --repository=*)
            REPOSITORY="${option#*=}"
            shift
            ;;
        --imageVersion=*)
            IMAGE_VERSION="${option#*=}"
            shift
            ;;
        --no-login)
            LOGIN=false
            shift
            ;;
        --lint)
            LINT=true
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
Deploys a mx_bluesky app (either hyperion or redis-to-murko) to kubernetes.

Important!
If you do not specify --checkout-to-prod YOU MUST run this from the mx_bluesky directory that will be bind-mounted to
the container, NOT the directory that you built the container image from.

Arguments:
  release                 Name of the helmchart release
  app_name                Use either "hyperion-supervisor" or "redis-to-murko"

Options:

  --help                  This help
  --imageVersion=version    Version of the image to fetch from the repository otherwise it is deduced
                          from the setuptools_scm. Must be in the format x.y.z
  -b, --beamline=BEAMLINE Overrides the BEAMLINE environment variable with the given beamline
  --dev                   Install to a development kubernetes cluster (assumes project checked out under /home)
                          (default cluster is argus in user namespace)
  --dry-run               Do everything but don't do the final deploy to k8s 
  --no-login              Do not attempt to log in to kubernetes instead use the current namespace and cluster
  --repository=REPOSITORY Override the repository to fetch the image from
  --lint                  Lint the helm chart
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
  if [[ "$APP_NAME" != "hyperion-supervisor" && "$APP_NAME" != "redis-to-murko" ]]; then
    echo "Invalid app name specified. Please provide either 'hyperion-supervisor' or 'redis-to-murko'."
    exit 1
  fi
fi


HELM_OPTIONS=""
PROJECTDIR=$(readlink -e $(dirname $0)/../..)
TOP_HELMCHART_DIR=${PROJECTDIR}/helm
HELMCHART_DIR=${TOP_HELMCHART_DIR}/${APP_NAME}

if [[ $LOGIN = true ]]; then
  if [[ -n $DEV ]]; then
    CLUSTER=argus
    NAMESPACE=$(whoami)
  else
    CLUSTER=k8s-$BEAMLINE
    NAMESPACE=$BEAMLINE-beamline
  fi
fi

if [[ -n $REPOSITORY ]]; then
  HELM_OPTIONS+="--set application.imageRepository=$REPOSITORY "
fi

echo "Container image version that will be pulled is $APP_VERSION"

#application.runAsUser=$EUID,\
#application.runAsGroup=$GID,\
#application.supplementalGroups=[$SUPPLEMENTAL_GIDS],\
#application.externalHostname=test-$APP_NAME.diamond.ac.uk "
if [[ -n $DEV ]]; then
  GID=`id -g`
  SUPPLEMENTAL_GIDS=37904
  HELM_OPTIONS+="--set \
application.dev=true,\
application.logDir=$PROJECTDIR/tmp,\
application.dataDir=$PROJECTDIR/tmp/data,\
stomp.url=tcp://rabbitmq-test:61613 "
fi

HELM_OPTIONS+="--set application.imageVersion=$IMAGE_VERSION "

module load helm

APP_VERSION=$IMAGE_VERSION

helm package $HELMCHART_DIR --app-version $APP_VERSION
# Helm package generates a file suffixed with the chart version
if [[ $LOGIN = true ]]; then
  module load $CLUSTER
  kubectl config set-context --current --namespace=$NAMESPACE
fi
if [[ $LINT = true ]]; then
  helm lint $HELMCHART_DIR $HELM_OPTIONS
elif [[ -z $DRY_RUN ]]; then
  helm upgrade --install $HELM_OPTIONS $RELEASE $APP_NAME-0.0.1.tgz
else
  echo "helm upgrade --install $HELM_OPTIONS $RELEASE $APP_NAME-0.0.1.tgz"
fi
