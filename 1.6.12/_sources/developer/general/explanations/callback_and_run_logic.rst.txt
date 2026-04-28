Callbacks and Run Logic
========================

Callbacks are used to trigger external services:

- Ispyb deposition
- Nexus writing
- Zocalo triggering

These are linked in that to trigger zocalo you need to have made an ispyb deposition, written a nexus file and have finished writing raw data to disk. Nexus files and ispyb depositions can be made at anytime, we do not need to have necessarily finished writing raw data. 

Currently, the requirement of needing to have written to ispyb is explicit as the ispyb callback will emit to the zocalo callback. The nexus file is written when the hardware is read during a collection and so its ordering is implied. When instantiated the zocalo callback is told on which plan to trigger and it is up to the plan developer to make sure this plan finishes after data is written to the detector.

In general, the ordering flow of when callbacks are triggered is controlled by emitting documents with the expected plan name and data.

Xray Centring
-------------
The xray centring code generally has three parts; detect the grid to flyscan over, do the fast grid scan, collect the data from zocalo and move to the centre it defines. It does this with the following runs:

1. ``CONST.PLAN.GRID_DETECT_AND_DO_GRIDSCAN`` is the outer run. When this starts it will deposit the initial ispyb information (but more is added as the collection continues)
2. ``CONST.PLAN.GRIDSCAN_OUTER`` is started after we have done the grid detection but before we do the work for setting up the gridscan. It is used to set transmission (and optionally feedback as per the selected preprocessors) and to initialise nexus writing (the final nexus file is only written when all the relevant data is read from the beamline)
3. ``CONST.PLAN.DO_FGS`` is the internal run that is opened just before the actual gridscan motion happens. The start of this will create the data to send to zocalo, zocalo is then triggered once all the (zocalo triggered by the hardware read)
4. ``CONST.PLAN.FLYSCAN_RESULTS`` is used to emit the results of the flyscan, that are then picked up by a ``XRayCentreEventHandler`` so that we can use them later in the plan.


Rotation Scans
---------------------

Rotation scans are generalised so that multiple scans can be done at once. The plan will create one hdf file for all rotations but then N nexus files, N ispyb depositions and triggers zocalo N times.

It does this by starting 1+2*N different runs:

1. ``CONST.PLAN.ROTATION_MULTI``: This is emitted once for the whole multiple rotation. It is used by the nexus callback to get the full number of images and meta_data_run_number so that it knows which hdf file to use. When this is finished zocalo end is triggered.
2. ``CONST.PLAN.ROTATION_OUTER``: Emitted N times, inside a ``CONST.PLAN.ROTATION_MULTI`` run. This is used to create the initial ispyb deposition and create the nexus writer (but not actually write the file)
3. ``CONST.PLAN.ROTATION_MAIN``: Emitted N times, inside ``CONST.PLAN.ROTATION_OUTER`` run. Used to finish writing to ispyb (i.e. write success/failure) and to send collection information to zocalo.

There is also a ``CONST.PLAN.ROTATION_MULTI_OUTER``, which is used when the rotation scan is run independently (i.e. outside of a bigger ``load_centre_collect``). This is needed as we need to activate the ``BeamDrawingCallback`` for this case.
