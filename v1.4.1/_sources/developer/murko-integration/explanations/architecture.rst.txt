Murko Architecture
------------------

The architecture of how Murko is integrated is still in flux but as of 07/08 the following has been tried on the beamline.

.. image:: ../images/murko_setup.drawio.png

The mx-bluesky code is deployed into the `beamline kubernetes cluster <https://k8s-i04.diamond.ac.uk/>`_ behind a `blueAPI <https://github.com/DiamondLightSource/blueapi>`_ REST interface. Alongside this an instance of murko is also deployed to the k8s cluster.

When GDA reaches a point where it will thaw the pin (usually just after robot load), if the ``gda.mx.bluesky.thaw`` property has been set to True it will instead call out to the thaw_and_center plan inside mx-bluesky.

The thawing plan will first create a ``MurkoCallback`` callback, this will stream metadata into a key in a redis database running on i04-control (this should be moved in `#145 <https://github.com/DiamondLightSource/mx-bluesky/issues/145>`_).

It will then trigger the ``OAVToRedisForwarder`` device in ``dodal`` that will stream image data to redis in the form of pickled RGB numpy arrays. Each image is given a uuid by this device, which is used to correlate the images with the other metadata, which could be streamed with a different frequency.

The image streaming must be done with an ophyd device as there is too much data for it all to be emitted in bluesky documents.

When the data is entered into redis it will publish a message to the redis ``murko`` channel. This will get picked up by the `socket_handler <https://github.com/DiamondLightSource/mx_auto_mjpeg_capture/tree/main/socket_handler>`_, which will forward the data to murko. Currently, during testing the socket_handler is just manually run on a workstation, `#146 <https://github.com/DiamondLightSource/mx-bluesky/issues/146>`_ should fix this.
