Containerised System Tests
==========================

System Test Runner
------------------

The system tests are run by a self-hosted `github actions runner`_.

.. _github actions runner: https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners

The runner is hosted on kubernetes. The docker image is hosted on ghcr.io can be built from the Dockerfile and scripts
in the ``system-test-image`` folder.

The actions runner registers itself with GitHub and its current status can be viewed by going to the 
mx-bluesky repository, clicking Settings and then going to Actions->Runners in the sidebar.

To rebuild the docker image and push it to ghcr.io, run 

::

    build.sh --push

Deploying to kubernetes
-----------------------

The ``system-test-image/helmchart`` folder contains a helmchart which can be used to deploy the test runner to a 
kubernetes cluster:

::

    module load argus
    module load helm
    helm upgrade mx-bluesky-system-test-runner ./helmchart --install  --namespace mx-bluesky

Rebuilding the kubernetes secrets
---------------------------------

The kubernetes deployment references the following secrets

* Github Personal Access Token - this is needed to register the action runner with GitHub
* IspyB tests database credentials

These can be refreshed using the following:

::

    kubectl create secret --namespace=mx-blueskygeneric ispyb-credentials --from-file=/dls_sw/dasc/mariadb/credentials/ispyb-hyperion-dev.cfg
    kubectl create secret --namespace=mx-bluesky generic tokens --from-literal=actionsRunnerToken=<your_PAT>
