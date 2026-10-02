Deploying Hyperion on Kubernetes
================================

Initial deployment
------------------

If deploying for the first time on a beamline, you will need to ensure that the following resources are present in the beamline namespace:

* Secrets: Similar to the blueapi deployment, you will require the following secrets to be present:
   * rmq-creds: Credentials for the zocalo rabbitmq instance
   * ispyb-hyperion-cfg: Credentials required for connecting to Expe-Eye
* A rabbitmq deployment <beamline>-rabbitmq - this is for internal communication between the supervisor, blueapi and the callbacks.

See  `Notes on the Hyperion K8s Deployment <../explanations/containerised_mx_bluesky.html>`_ for a more detailed description of the deployment.

Setting up beamline services and deployments repositories
---------------------------------------------------------

Deployment of hyperion is via ArgoCD and is enabled by creating an ``ixx-hyperion`` folder in the relevant ``ixx-services`` ``services/`` folder.

For an example see the i03 deployment at https://gitlab.diamond.ac.uk/controls/containers/beamline/i03-services

This will then need to be enabled by referencing it in the corresponding ``ixx-deployment`` ``apps/values.yaml``.

Upgrading Hyperion to a newer version
-------------------------------------

In order to deploy a newer version of Hyperion you should make the following changes:
  * ``services/ixx-hyperion/values.yaml`` - edit the ``hyperion.application.imageVersion`` with the updated hyperion container image version. Also update ``hyperion.initContainer.dodalBranch`` with the dodal git tag that the initContainer should check out to scratch.
  * ``services/ixx-hyperion/Chart.yaml`` - Update dependencies.version for hyperion to the corresponding version of the ``hyperion`` helm chart.

The above images and helm charts should be published on every release to `GHCR repository <https://github.com/orgs/DiamondLightSource/packages?repo_name=mx-bluesky>`_.

Push these changes to the services repository. ArgoCD will detect the changes and deploy a new image.

In the event that other configuration changes are made which don't require a new release, for most changes ArgoCD will detect a change in values.yaml and restart the deployment if necessary. However certain changes may result in the container configuration being updated live and so the pod will not restart. Hyperion will generally require a restart for such changes as it does not monitor the filesystem and for this it is sufficient to delete the pod from the Kubernetes dashboard which will result in the pod being recreated.

When updating to a new version, note that the Persistent Volume Claim (PVC) for the scratch folder for the old version will not be removed - this is so that if reversion to the previous version is required the image is still present. In order to prevent a buildup of volumes, when they are no longer needed any live changes to the scratch folder should have PRs made for them if necessary and the PVCs manually deleted.
