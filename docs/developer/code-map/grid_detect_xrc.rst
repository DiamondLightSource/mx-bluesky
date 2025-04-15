Grid Detect Then Xray Centre
============================

The aim of this page is to provide a general overview of the Hyperion ``grid_detect_then_xray_centre_plan``.

Most of the code for the ``grid_detect_then_xray_centre_plan`` plan is in ``mx-bluesky/hyperion``. Some code is located in ``mx-bluesky/common`` and `dodal <https://github.com/DiamondLightSource/dodal>`_, and plans are increasingly being generalised and moved into ``mx-bluesky/common`` where possible. Therefore, the structure of the codebase is subject to change and this document should be updated accordingly.

There are then a number of plans that make up the ``grid_detect_then_xray_centre_plan`` plan. Some important ones:

* :ref:`grid_detection_plan<grid-detect>` - Use the OAV to optically calculate a grid for a scan that would cover the whole sample.
* :ref:`flyscan_xray_centre_plan<flyscan>` - Triggers a hardware-based grid scan and moves to the X-ray centre as returned from ``zocalo``.
* :ref:`grid_detect_then_xray_centre_plan<grid-detect-xrc>` - This top-level plan performs an :ref:`OAV grid detection <grid-detect>` then a :ref:`flyscan x-ray centre <flyscan>`.

The diagram below shows all the plans that make up the ``grid_detect_then_xray_centre_plan``. The colors indicate where these plans can be found.

.. image:: grid_detect_then_xray_centre.drawio.png

.. _grid-detect-xrc:

Grid Detect Then Xray Centre Plan
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`This plan <https://github.com/DiamondLightSource/mx-bluesky/blob/main/src/mx_bluesky/hyperion/experiment_plans/grid_detect_then_xray_centre_plan.py>`__ does the following, in roughly this order:

1. If called standalone, start preparing for data collection.
2. Perform an :ref:`OAV grid detection <grid-detect>`.
3. Convert the parameters calculated in step 2 into something we can send to the flyscan X-ray centre.
4. Move the backlight out, set the aperture to small, and wait for the detector to finish moving.
5. Perform a :ref:`flyscan X-ray centre <flyscan>`.
6. Move the sample based on the results of step 5.

.. _grid-detect:

OAV Grid Detection
~~~~~~~~~~~~~~~~~~

`This plan <https://github.com/DiamondLightSource/mx-bluesky/blob/main/src/mx_bluesky/hyperion/experiment_plans/oav_grid_detection_plan.py>`__ does the following, in roughly this order:

1. Move to omega 0.
2. Calculate the 2D grid size using the edge arrays from the OAV.
3. Trigger the OAV device to take snapshots, both with and without the grid.
4. Read the snapshot paths (which will be gathered for ispyb in the background).
5. Repeat steps 2–4 for omega 90.
6. Return the grid positions.

.. _flyscan:

Flyscan Xray Centre No Move
~~~~~~~~~~~~~~~~~~~~~~~~~~~

`This plan <https://github.com/DiamondLightSource/mx-bluesky/blob/main/src/mx_bluesky/hyperion/experiment_plans/flyscan_xray_centre_plan.py>`__ does the following, in roughly this order:

1. Move to the desired transmission (and turn off xbpm feedback).
2. Move to omega 0.
3. Read hardware values for ispyb (a grid scan entry will be added in the background).
4. Set up zebra and motion devices for a grid scan to be done in the motion controller.
5. Wait for the Eiger to finish arming or arm the Eiger if it hasn't already been done.
6. Run the motion control grid scan.
7. Wait for the grid scan to end.
8. Retrieve the X-ray centering results from ``Zocalo`` (which will be gathered in the background).
