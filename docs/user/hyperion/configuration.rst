Configuration
-------------

Hyperion main configuration
===========================

Configuration of several properties that control Hyperion execution are available. These can be edited in the 
``domain.properties`` file typically found in

::

    /dls_sw/<beamline>/software/daq_configuration/domain.properties

Note that making a change to these properties generally requires a restart of the GDA server.


.. csv-table:: Configuration properties
    :widths: auto
    :header: "Property Name", "Type", "Description"

    "gda.gridscan.hyperion.flaskServerAddress", "host:port", "Configures the Hyperion server address that GDA connects to."
    "gda.gridscan.hyperion.multipin", "boolean", "Controls whether multipin collection is enabled."
    "gda.hyperion.use_grid_snapshots_for_rotation", "boolean", "If true, then rotation snapshots are generated from the grid snapshots instead of directly capturing them"
    "gda.mx.hyperion.enabled",  "boolean",  "Controls whether GDA invokes Hyperion or performs collection itself"
    "gda.mx.hyperion.panda.runnup_distance_mm", "double", "Controls the panda runup distance."
    "gda.mx.hyperion.xrc.box_size", "double", "Configures the grid scan box size in microns."
    "gda.mx.hyperion.use_panda_for_gridscans", "boolean", "If true then the Panda is used instead of the Zebra for XRC gridscans" 
    "gda.mx.hyperion.xrc.use_gpu_results", "boolean", "If true, then zocalo gridscan processing uses the GPU results"
    "gda.mx.hyperion.xrc.use_roi_mode", "boolean", "If true then ROI mode is used."
    "gda.mx.udc.hyperion.enable", "boolean",  "Enables Hyperion UDC mode."

Beamline configuration/calibration files
========================================

Hyperion makes use of other beamline configuration and calibration files which are also currently stored in 

::

    /dls_sw/<beamline>/software/daq_configuration

These are currently shared with GDA, so changes to these files will affect both applications.

Config Server
=============

If the `Config Server`_ is deployed and running, Hyperion is configured to use it in preference to reading the 
``domain.properties`` file directly. However in the event of the config server being unavailable Hyperion will fall
back to reading it from the filesystem.

Note that currently the rest of the configuration files are not read from the config server, but the intention is that 
ultimately it will be the source of all configuration and the remainder of the files in ``daq_configuration`` will be
moved over to it.

.. _Config Server: https://github.com/DiamondLightSource/daq-config-server/
