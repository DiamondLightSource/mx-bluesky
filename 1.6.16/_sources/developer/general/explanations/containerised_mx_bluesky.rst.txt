Containerised mx-bluesky
========================

There are currently two images associated with this repository which are pushed on release: hyperion, and mx-bluesky-blueapi.

The Hyperion image exists because Hyperion was developed before BlueAPI was production-ready, and so doesn't use BlueAPI to schedule plans. This image is only really relevant for i03, and currently isn't used in production anywhere

The ``mx-bluesky-blueapi`` image exists as a minor extension of BlueAPI's image. BlueAPI's image contains the dependencies of BlueAPI, as well as the dependencies of BlueAPI, which includes dodal. When the BlueAPI service is launched, it will do a ``pip install --no deps`` of the plan repository. For MX, this means ``mx-bluesky`` gets installed without any of its dependencies. For this reason, we have created an ``mx-bluesky-blueapi`` image which installs these extra dependencies. 

This image can be used with BlueAPI's original helmchart, the only change required in the ``values.yaml`` is::

    image:
        repository: ghcr.io/diamondlightsource/mx-bluesky-blueapi
        tag: "{desired_version}"
