Containerised mx-bluesky
========================

There are currently two images associated with this repository which are pushed on release: hyperion, and mx-bluesky-blueapi.

The Hyperion image is the image that provides ``hyperion-supervisor`` and ``hyperion-callbacks``. These are launched as applications in their own right; ``hyperion-supervisor`` makes use of BlueAPI client but does not expose blueapi plans. ``hyperion-callbacks`` does not use BlueAPI. Which application is launched depends on whether ``hyperion`` or ``hyperion-callbacks`` is specified in the container launch command.

The ``mx-bluesky-blueapi`` image exists as a minor extension of BlueAPI's image. BlueAPI's image contains the dependencies of BlueAPI, as well as the dependencies of BlueAPI, which includes dodal. When the BlueAPI service is launched, it will do a ``pip install --no deps`` of the plan repository. For MX, this means ``mx-bluesky`` gets installed without any of its dependencies. For this reason, we have created an ``mx-bluesky-blueapi`` image which installs these extra dependencies.

This image can be used with BlueAPI's original helmchart, the only change required in the ``values.yaml`` is::

    image:
        repository: ghcr.io/diamondlightsource/mx-bluesky-blueapi
        tag: "{desired_version}"

``hyperion-blueapi`` is launched as a standard ``mx-bluesky-blueapi`` image with configuration to load the hyperion plan and beamline modules.

Notes on the hyperion k8s deployment
------------------------------------

The hyperion Kubernetes deployment consists of a singled pod in a deployment which has 4 containers:

* ``hyperion-init``, an initContainer which runs before all other containers start.
* ``hyperion-supervisor`` which launches the supervisor
* ``hyperion-callbacks`` which launches the external callbacks
* ``hyperion-scratch`` which is present to enable hotfixes to be applied

The base ``hyperion`` container image contains only ``mx-bluesky`` and ``dodal`` bare git repos, plus the python virtual environment which provides all other library dependencies. When a new release of ``hyperion`` is first deployed to the cluster, it creates an empty Persistent Volume Claim (PVC).

``hyperion-init`` runs on pod startup and is responsible for checking out ``dodal`` and ``mx-bluesky`` to the persistent volume if they do not already exist.

``hyperion-supervisor`` and ``hyperion-callbacks`` then mount the persistent volume read-only under ``/scratch``, and then run ``hyperion`` from this.

``hyperion-scratch`` is a container that has the persistent volume mounted read-write, its only purpose is to wait for VSCode to attach to it so that you can edit the writable PVC; since ordinary ephemeral containers cannot mount PVCs directly. In this manner, hot fixes to the code can be applied either by editing in VSCode, or via the console; when the pod is restarted the changes will be retained.
