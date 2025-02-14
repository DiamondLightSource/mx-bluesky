Run a collection
--------------------

Starting the EDM screens
========================

A couple of entry points have been set up so that:

-  ``run_fixed_target`` starts the edm screens for a fixed target
   collection
-  ``run_extruder`` starts the edm screens for a serial jet collection

Before opening the experiment specific edm, each of these entry points
will start a ``BlueAPI`` server. The configuration used by ``BlueAPI``
is saved in ``src/mx_bluesky/beamlines/i24/serial/blueapi_config.yaml``.

Detector choice
===============

The detector currently in use is identified by reading the position of
the detector stage in the y direction. A different detector can be chose
by opening the ``Detector`` tab in the main edm screen, selecting the
detector name from the list and clicking the ``Move Stage`` button,
which will move the detector stage to the correct height and update the
relative PVs.

Detectors available for serial: Pilatus 6M or Eiger CdTe 9M.

Extruder (Serial Jet)
=====================

On startup, once both the visit and the detector have been set up,
**always** press the ``initialise on start`` button, which will autofill
the general purpose PVs for an extruder collection with sensible default
values, as well as the chosen visit directory and detector. Ensure that
the visit shown on the edm screen is correct.

I - **Align Jet**

Open the viewer and switch on the backlight to visualise the jet stream.
You can use the positioners in the ``Align Jet`` panel on the edm screen
to move the orizontal goniometer table and align the jet.

II - **Set experiment parameters**

1. Data collection set up

In the edm screen fill the fields in ``Data Collation Setup`` with
information such as sub-directory, filename, number of images, exposure
time and detector distance. It is recommended to not collect all data
into a single sub-directory but split into multiple smaller collections.

2. Pump Probe

For a pump-probe experiment, select ``True`` on the dropdown menu in
``Data Collection Setup`` and then set the laser dwell and delay times
in the ``Pump Probe`` panel. 

**WARNING** This setting requires a
hardware change, as there are only 4 outputs on the zebra and they are
all in use. When using the Eiger the Pilatus trigger cable should be
used to trigger the light source. When using the pilatus the eiger
trigger cable should be used.

III - **Run collection**

Once all parameters have been set, press ``Start`` to run the
collection. A stream log will show what is going on in the terminal.

Fixed-Target (Serial Fixed)
===========================

I - **Make coordinate system**

Generally the first thing to do before running a chip collection is to
set up the coordinate system.

Before this step remember to reset the scale and skew factors as well as
the motor directions as needed. Current values are saved in
``src/mx_bluesky/beamlines/i24/serial/parameters/fixed_target`` in the
``cs_maker.json`` and ``motor_direction.txt`` files.

1. From the main edm screen open the ``viewer`` and ``moveonclick``.
2. Find the first fiducial in the top left corner, centre it and press
   ``set fiducial 0``.
3. Move to Fiducial 1 and 2 and repeat the process.
4. Once all fiducials have been set, press ``make coordianates system``.
   If all worked correctly it will find the first window in the first
   block.
5. Run ``block check`` to check that all blocks are correctly aligned.
   WARNING: ``block check`` is not available for a custom chip.

II - **Select experiment parameters**

1. In the edm screen fill the fields in
   ``Chip and Data Collation Setup`` with information such as
   sub-directory, filename, exposure time and detector distance.

2. Select chip and map type

Select the ``Chip Type`` from the drop-down menu on the edm screen.
Currently available chips: 0. Oxford 1. Oxford Inner 2. Custom 3.
Minichip

When using a non-custom chip ``Map Type`` should always be selected, for
other chips it’s only necessary when wanting to collect only on selected
blocks.

-  For a full-chip collection on an Oxford-type chip, ``Map Type``
   should simply be set to ``None``.
-  For a Custom Chip, click on the ``Custom Chip`` button, which will
   bring up the relative edm. Here, the steps are the following:

   1. Clear Coordinate System. This will reset the coordinates.
   2. Fill in the fields for number of windows and step size in x/y
      direction.
   3. Press ``Set current position as start``.
   4. Once finished, close and return to main screen.

-  For collecting only on specific windows on an Oxford chip:

   1. Set the ``Mapping Type`` to ``Lite``. This will make the Lite
      launchers button visible.
   2. On the launcher, select the blocks to collect - either manually or
      using a preset set.
   3. Run ``Save Screen Map``. This will create a ``currentchip.map``
      file which will be copied to the data directory at collection
      time.
   4. Run ``Upload Parameters``.
   5. Once finished, close and return to main screen.

3. Select pump probe

After setting the exposure time, open ``Pump Probe`` screen from main
edm. The box will appear by selecting one of the settings from the drop
down menu.

-  ``Short1`` and ``Short2``: once opened set the laser dwell and delay
   times.
-  ``Repeat#``: Set laser dwell and press calculate to get the delay
   times for each repeat mode.
-  ``Medium1``: open and close fast shutter between exposures, long
   delays between each one.

Select the most appropriate pump probe setting for your collection and
set the laser dwell and delay times accordingly.

For more details on the pump probe settings see `Dynamics and fixed
targets <https://confluence.diamond.ac.uk/display/MXTech/Dynamics+and+fixed+targets>`__


III - **Run a collection**

Once all parameters have been set, press ``Start`` to run the
collection. A stream log will show what is going on in the terminal.


**NOTE** As of version ``1.0.0``, the ``Set parameters`` button has been removed and
the parameters will now be read from the edm and applied to the collection directly
once the ``Start`` button is pressed. For previous versions however, the button must
still be pressed before starting the collection. A copy of the parameter file and chip
map (if applicable) will still be saved in the data directory at collection time.
