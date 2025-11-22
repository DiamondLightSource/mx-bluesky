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

``hyperion-blueapi`` is automatically available in a standard Hyperion deployment.

Launching
---------

``hyperion-blueapi`` can be launched in using the ``run_hyperion.sh`` script, using the ``--blueapi`` option:

::

    ./run_hyperion.sh --beamline=i03 --dev --blueapi
