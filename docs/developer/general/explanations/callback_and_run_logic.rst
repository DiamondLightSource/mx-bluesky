Callbacks and Run Logic
========================

Callbacks are used to trigger external services:

- Ispyb deposition
- Nexus writing
- Zocalo triggering

These are linked in that to trigger zocalo you need to have made an ispyb deposition, written a nexus file and have finished writing raw data to disk. Nexus files and ispyb depositions can be made at anytime, we do not need to have necessarily finished writing raw data. 

Currently, the requirement of needing to have written to ispyb is explicit as the ispyb callback will emit to the zocalo callback. The nexus file is written when the hardware is read during a collection and so its ordering is implied. When instantiated the zocalo callback is told on which plan to trigger and it is up to the plan developer to make sure this plan finishes after data is written to the detector.

In general, the ordering flow of when callbacks are triggered is controlled by emitting documents with the expected plan name and data.

Rotation Scans
---------------------

There are currently two ways of doing rotation scans. A single scan creates one hdf file, one ispyb deposition and then triggers zocalo once. Multi rotation scans create one hdf file for all rotations but then N nexus files, N ispyb depositions and triggers zocalo N times.

Single scans will be removed in https://github.com/DiamondLightSource/mx-bluesky/issues/847

For multi rotations this is does by starting 1+2*N different runs:

1. ``CONST.PLAN.ROTATION_MULTI``: This is emitted once for the whole multiple rotation. It is used by the nexus callback to get the full number of images and meta_data_run_number so that it knows which hdf file to use. When this is finished zocalo end is triggered.
2. ``CONST.PLAN.ROTATION_OUTER``: Emitted N times, inside a ``CONST.PLAN.ROTATION_MULTI`` run. This is used to create the initial ispyb deposition and create the nexus writer (but not actually write the file)
3. ``CONST.PLAN.ROTATION_MAIN``: Emitted N times, inside ``CONST.PLAN.ROTATION_OUTER`` run. Used to finish writing to ispyb (i.e. write success/failure) and to send collection information to zocalo.
