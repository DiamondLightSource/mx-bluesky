Configuration
-------------

Hyperion main configuration
===========================

Configuration of several properties that control Hyperion execution are available. These can be edited in the 
``domain.properties`` file typically found in

::

    /dls_sw/<beamline>/software/daq_configuration/domain.properties

Note that making a change to these properties generally requires a restart of the GDA server.

Also note that some of these configuration properties will be removed in a future release of Hyperion. 

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
    "gda.mx.udc.hyperion.enable", "boolean",  "Enables Hyperion UDC mode in GDA - with this turned off, legacy UDC is performed by GDA."
    "gda.mx.hyperion.enable_beamstop_diode_check", "boolean", "If true, enables an extended beamstop position check
 during UDC default state script measuring the diode current out-of and in beam. Otherwise the beamstop position is
 moved to the data collection position."

Beamline configuration/calibration files
========================================

Hyperion makes use of other beamline configuration and calibration files which are also currently stored in 

::

    /dls_sw/<beamline>/software/daq_configuration

These are currently shared with GDA, so changes to these files will affect both applications.

Config Server
=============

Hyperion is configured to use the daq-config-server to read the ``domain.properties`` and ``beamlineParameters`` files.
These are read through a client that caches requests to reduce load on the server. When either of these files is changed,
the cache needs to be cleared before the changes will be picked up. To do this, when in in-process UDC mode, restart
Hyperion. When in blueapi mode, restart the blueapi environment.

Note that currently the rest of the configuration files are not read from the config server, but the intention is that 
ultimately it will be the source of all configuration and the remainder of the files in ``daq_configuration`` will be
moved over to it.

See `Config Server`_ for details of the config server and how it is configured and deployed.

.. _Config Server: https://github.com/DiamondLightSource/daq-config-server/

See also `Advanced Configuration`_ for details of configuration performed at deployment time.

.. _`Advanced Configuration`: advanced/advanced_configuration.html
