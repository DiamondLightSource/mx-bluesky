Configuration
-------------

Configuration of several properties that control Hyperion execution are available. These can be edited in the 
``domain.properties`` file typically found in

::

    /dls_sw/<beamline>/software/daq_configuration/domain.properties


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
    "gda.mx.udc.hyperion.enable", "boolean",  "Enables baton passing to Hyperion."
