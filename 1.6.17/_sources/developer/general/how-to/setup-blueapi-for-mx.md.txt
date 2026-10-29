# Setting up BlueAPI for an MX beamline

## Background

The Athena DAQ platform is intended to run in microservices using kubernetes. A beamline ixx has a gitlab repository `ixx-services`, which contains that beamline's available services and their helm configurations, as well as `ixx-deployments` which says which available services should be deployed. Services managed in this way will be deployed into the `ixx-beamline` namespace. ArgoCD provides a useful dashboard for the deployed services and their kubernetes objects. See [here](https://dev-guide.diamond.ac.uk/athena/how-tos/migration/) for more information. This guide will explain how to setup BlueAPI using mx-bluesky within this framework.

## Prerequisites

1. The beamline has a kubernetes cluster with gitlab deployment and services repos. See [here](https://dev-guide.diamond.ac.uk/epics-containers/how-tos/intro/) for a guide on this. DAQ members should be codeowners of these repos.
2. Confirm the beamline cluster has a Blueapi ingress and DNS entry for `ixx-blueapi.diamond.ac.uk` - create a scicomp ticket if it doesn't.

## Guide to run BlueAPI with mx-bluesky through kubernetes

The best way to add BlueAPI to the services and deployments repo with the correct configuration is to copy from an existing setup and change the relevant values. i04 will be used as an example for this guide - [see their blueapi configuration](https://gitlab.diamond.ac.uk/controls/containers/beamline/i04-services/-/tree/main/services/i04-blueapi?ref_type=heads). The `chart.yaml` tells us which helmcharts are being used. The BlueAPI helmchart gives us the bulk of the configuration. See [here](https://github.com/DiamondLightSource/blueapi/tree/main/helm/blueapi) for a table of its settings. In MX we use an additional `mx-bluesky-blueapi` helmchart - right now this is purely for configuring Zocalo, but anything else which is generic to MX should be added.

`values.yaml` lets us configure the helmcharts that we had listed in dependencies. This file should look the same for each MX beamline, other than the actual beamline name. Unfortunately, there's no way to get a templated file here which automatically fills in the beamline name. Some notes:

- The BlueAPI image should be set to `ghcr.io/diamondlightsource/mx-bluesky-blueapi` and you should specify a version tag. See all releases of this image [here](https://github.com/DiamondLightSource/mx-bluesky/pkgs/container/mx-bluesky-blueapi). This image will install any MX-specific dependencies on top of the BlueAPI image.
- We are currently mounting `/dls/ixx` and `/dls_sw/ixx` to BlueAPI, but the long-term goal is to not mount the file system. Nexgen currently requires `/dls/ixx` to be mounted. Once Nexgen is migrated into a separate service, we can unmount `/dls/ixx` from Blueapi and mount it in Nexgen only. Unmounting `/dls_sw/ixx`requires us to be using the config server for all settings - this is currently being worked on.
- Until the above is done, BlueAPI needs to run as the detector user so that it has permission to write files. Type `id ixxdetector` into a terminal to find the user id. This then needs to be added in the `runAsUser: [number]` part of the values.

MX Bluesky plans require some secrets to be added to the beamline cluster. The configuration from the above requires these secrets, so will not work without this. At the time of writing this guide, there are 3 that we need: ispyb (expeye) credentials, rabbitMQ credentials for zocalo, and config for rabbitMQ api reader for zocalo. These should be added as sealed secrets and committed to the services repo. Here's how this works:

1. Open a terminal and enter your beamline cluster with `module load k8s-ixx`
2. Set the default namespace to ixx-beamline with `kubectl config set-context --current --namespace=ixx-beamline`
3. Create a regular secret and save to a yaml file with `kubectl create secret generic [secret-name] --from-file=/path/to/sensitive/file --save-config --dry-run=client -o yaml > [secret-file-name.yaml]`
4. Seal the secret with `kubeseal --controller-namespace kube-system --controller-name sealed-secrets-controller --format yaml < [secret-file-name.yaml] > [sealed-secret-file-name.yaml]`. This will encrypt your secret - the beamline cluster comes installed with the private key to decrypt information sealed with this command.
5. Commit the sealed secret into `ixx-services/services/ixx-blueapi/templates`. Importantly, do not commit the unsealed secret!
6. Once this is pushed to the main branch, you can check the k8s dashboard to see if the secret has successfully been added.

<div style="border: 2px solid #f39c12; background-color: #fef2e4; padding: 10px; margin: 15px 0; border-radius: 5px;">
  <strong>Warning:</strong> The mx-bluesky-blueapi image is responsible for your blueapi version and your python environment. It is independent from the mx-bluesky and dodal repos in the scratch folder. Currently, the versions of these repos must be manually managed. This will be addressed <a href="https://github.com/DiamondLightSource/blueapi/issues/933" target="_blank" style="color: #e67e22; text-decoration: underline;">here</a>. 
</div>

Paths to required credentials:

- Zocalo api reader: `/dls_sw/apps/zocalo/secrets/rabbitmq-api-reader.yml`
- Zocalo RMQ credentials: `/dls_sw/apps/zocalo/secrets/rabbitmq-credentials.yml`
- ispyb (expeye) credentials: `/dls_sw/dasc/mariadb/credentials/ispyb-mx-bluesky-ixx.cfg`
  See [here](https://gitlab.diamond.ac.uk/controls/containers/beamline/i24-services/-/tree/main/services/i24-blueapi/templates?ref_type=heads) For what the templates folder should look like once the above steps have been done.
