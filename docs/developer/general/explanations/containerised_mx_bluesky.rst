Containerised mx-bluesky
========================

There are currently two images associated with this repository which are pushed on release: hyperion, and mx-bluesky-blueapi.

The Hyperion image is the image that provides ``hyperion-supervisor`` and ``hyperion-callbacks``. These are launched as applications in their own right; ``hyperion-supervisor`` makes use of BlueAPI client but does not expose blueapi plans. ``hyperion-callbacks`` does not use BlueAPI. Which application is launched depends on the arguments passed to the ``entrypoint.sh`` launcher script on container startup.

The ``mx-bluesky-blueapi`` image exists as a minor extension of BlueAPI's image. BlueAPI's image contains the dependencies of BlueAPI, as well as the dependencies of BlueAPI, which includes dodal. When the BlueAPI service is launched, it will do a ``pip install --no deps`` of the plan repository. For MX, this means ``mx-bluesky`` gets installed without any of its dependencies. For this reason, we have created an ``mx-bluesky-blueapi`` image which installs these extra dependencies.

This image can be used with BlueAPI's original helmchart, the only change required in the ``values.yaml`` is::

    image:
        repository: ghcr.io/diamondlightsource/mx-bluesky-blueapi
        tag: "{desired_version}"

``hyperion-blueapi`` is launched as a standard ``mx-bluesky-blueapi`` image with configuration to load the hyperion plan and beamline modules.
