Hyperion on BlueAPI
===================

This document describes the migration of Hyperion from a monolithic service that contains its own application server 
and is only partially dependent on BlueAPI, 
to a standard BlueAPI application deployment. 

Architecture
------------

Hyperion on BlueAPI consists of two components:

* hyperion-blueapi: This is intended to ultimately be a standard blueapi installation, consisting of a beamline 
  module and a dodal plan module. In the interim, deployment may vary from the standard method until such time as 
  monolithic operation can be desupported. ``hyperion-blueapi`` exposes a minimal set of bluesky plans for UDC data 
  collection.

* hyperion-supervisor: This will be a separate service that is responsible for fetching instructions from 
  Agamemnon, decoding them and sending corresponding requests to ``hyperion-blueapi`` for execution. The supervisor
  also monitors the state of ``hyperion-blueapi``, manages the Hyperion baton and provides endpoints for status
  monitoring.

Deployment
----------

``hyperion-blueapi`` and ``hyperion-supervisor`` are automatically available in a standard Hyperion deployment.

Launching
---------

``hyperion-blueapi`` can be launched in using the ``run_hyperion.sh`` script, using the ``--blueapi`` option:

::

    ./run_hyperion.sh --beamline=i03 --dev --blueapi


``hyperion-supervisor`` can be launched using the ``run_hyperion.sh`` script, using the ``--supervisor`` option:

::

    ./run_hyperion.sh --beamline=i03 --dev --supervisor

Configuration
-------------

Configuration of ``hyperion-blueapi`` and ``hyperion-supervisor`` is done via standard BlueAPI .yaml configuration files.
Basic configuration files for i03 are supplied as follows in ``src/mx_bluesky/hyperion``.

.. csv-table:: hyperion-blueapi configuration files
    :widths: auto
    :header: "File", "Description"

    "blueapi_config.yaml", "Defines beamline device module and blueapi plans to be exported, BlueAPI REST to listen on, Stomp and graylog servers."


.. csv-table:: hyperion-supervisor configuration files
    :widths: auto
    :header: "File", "Description"

    "supervisor/client_config.yaml", "Tells the supervisor how to communicate with hyperion-blueapi, specifying the REST endpoint and stomp server."
    "supervisor/supervisor_config.yaml", "Configures the internal blueapi context with a minimal beamline module containing the baton device and the graylog endpoint."

When these are  deployed in kubernetes it is anticipated that these will be provided by specifying
directly in the values.yaml which will be expanded by the base helmcharts at deployment time.
