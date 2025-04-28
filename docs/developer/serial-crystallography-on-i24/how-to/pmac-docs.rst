=================================
PMAC-run operations on I24 serial
=================================


Several operations in a fixed target (FT) collection are run vie the PMAC, by sending a command to the ``PMAC_STRING`` PV.

Among these:

- Stage moves
- Kickoff data collection
- Laser control


For reference, see also the PMAC device implementation in dodal: `PMAC docs <https://diamondlightsource.github.io/dodal/main/reference/generated/dodal.devices.i24.pmac.html>`_


Stage motor moves using the PMAC device
---------------------------------------

Notes on PMAC coordinate system and motors
==========================================

In a PMAC, motors that should move in a coordinated fashion ware put
into the same coordinate system that can run a motion program. Motors
that should move independently of each other should go into a separate
coordinate system. A coordinate system is established by assigning axes
to motors. The axes allocations defined for the chip stages set up are:

::

   #1->X
   #2->Y
   #3->Z

When an X-axis move is executed, the #1 motor will make the move.

It should be noted that the PMAC coordinate system used by I24 serial is number 2, which can be specified in a PMAC string by starting the command with ``&2``.

When running chip collections, the stage motors are moved via the `PMAC
device <https://github.com/DiamondLightSource/dodal/blob/main/src/dodal/devices/i24/pmac.py>`__
in a couple of different ways.

1. In most cases, the {x,y,z} motors are moved by sending a command to
   the PMAC as a ``PMAC_STRING``.

   -  Using a JOG command ``J:{const}``, to jog the motor a specified
      distance from the current position. For example, this will move
      motor Y by 10 motor steps:

      .. code:: python

         yield from bps.abs_set(pmac.pmac_string, "#2J:10")


   -  The ``hmz`` strings are homing commands which will reset the
      encoders counts to 0 for the axis. All three motors are homed by
      sending the string: ``#1hmz#2hmz#3hmz``. In the plans this is done
      by triggering the home move:

      .. code:: python

         yield from bps.trigger(pmac.home)


   -  Another pmac_string that can start a move has the format
      ``!x..y..``. This is a command designed to blend any ongoing move
      into a new position. A common one through the serial collection
      code is ``!x0y0z0``, which will start a move to 0 for all motors.

      .. code:: python

         yield from bps.trigger(pmac.to_xyz_zero)


2. The stage motors can also be moved directly through the existing PVs
   ``ME14E-MO-CHIP-01:{X,Y,Z}``, for example:

   .. code:: python

      yield from bps.mv(pmac.x, 0, pmac.y, 1)


Notes on the coordinate system for a fixed-target collection
============================================================

CS_MAKER: Oxford-type chips (Oxford, Oxford-Inner, Minichip)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Generally, the first step before a chip collection is to create the
coordinate system. This is done by first selecting the 3 fiducials on
the and then clicking the ``Make co-ordinate system`` button. This
button runs the ``cs_maker`` plan, which computes the correct
pmac_strings to assign axes values to each motors.

Theory for this computation

::

   Rx: rotation about X-axis, pitch
   Ry: rotation about Y-axis, yaw
   Rz: rotation about Z-axis, roll
   The order of rotation is Roll->Yaw->Pitch (Rx*Ry*Rz)
   Rx           Ry          Rz
   |1  0   0| | Cy  0 Sy| |Cz -Sz 0|   | CyCz        -CxSz         Sy  |
   |0 Cx -Sx|*|  0  1  0|*|Sz  Cz 0| = | SxSyCz+CxSz -SxSySz+CxCz -SxCy|
   |0 Sx  Cx| |-Sy  0 Cy| | 0   0 1|   |-CxSyCz+SxSz  CxSySz+SxCz  CxCy|

   Skew:
   Skew is the difference between the Sz1 and Sz2 after rotation is taken out.
   This should be measured in situ prior to expriment, ie. measure by hand using
   opposite and adjacent RBV after calibration of scale factors.

The plan needs information stored in a few files:

* The motor directions are stored in ``src/mx_bluesky/i24/serial/parameters/fixed_target/cs/motor_direction.txt.`` The motor number multiplied by the motor direction should give the positive chip direction.
* The scale values for x,y,z, the skew value and the sign of Sx, Sy, Sz are all stored in ``src/mx_bluesky/i24/serial/parameters/fixed_target/cs/cs_maker.json``
* The fiducials 1 and 2 positions are written to file when selecting the fiducials (Setting fiducial 0 instead sends a homing command directly to the pmac_string PV)

NOTE. The ``motor_direction.txt`` and ``cs_maker.json`` files should
only be modified by staff when needed (usually when the stages have been
off for awhile).

CS_RESET: Custom chips
^^^^^^^^^^^^^^^^^^^^^^

When using a Custom chip, open the ``Custom chip`` edm and before doing
anything else click the ``Clear coordinate system`` button. This will
ensure that any pre-existing coordinate system from pre-vious chip
experiments is wiped and reset.

This operation is done by the ``cs_reset`` plan, which sends
instructions to the PMAC device to assign coordinates to each motor via
the following pmac_strings:

::

   "#1->10000X+0Y+0Z"
   "#2->+0X-10000Y+0Z"
   "#3->0X+0Y-10000Z"




Data collection via the PMAC
----------------------------

The data collection for a FT experiment is kicked off by sending a PMAC_STRING with the program number of the motion program the PMAC should run.

Two P-variables - general purpose variables that can be used to store information on the PMAC - have been set aside to monitor the collection run:

::

   P2401 is the "scan_status" variable. It goes to 1 once the motion program starts and will go back to 0 at the very end of the collection
   P2402 is the "counter" variable. It keeps count of how many images have been acquired so far in the collection.


The program number is chosen depending on the input collection parameters:

::

   11 -> Custom, Mini and PSI type chip collections, as well as Oxford chips with mapping set to "None" (full chip collections)
   12 -> Oxford Chips with Lite mapping (only some blocks collected)
   13 -> In the past was used for "Full Mapping". **CURRENTLY DISABLED**
   14 -> Any Pump Probe collection, with any chip type. **WARNING** Assumes Lite mapping for Oxford chips.

To do this, the PMAC device in dodal implements a Flyable device (``ProgramRunner``) and a soft signal (``program_number``).
The ``kickoff_and_complete_collection_plan`` first sets up the PMAC by setting the program_number signal and calculating the expected duration of the collection, and then triggers the collection by:

.. code:: python

   yield from bps.kickoff(pmac.run_program, wait=True)
   yield from bps.complete(pmac.run_program, wait=True)


The ``kickoff`` method works out the pmac_string to send from the program number in the following way:

::

   "&2b{prog_num}r" where
      - &2 is the coordinate system in use
      - b sets the motion program to run
      - r runs it


and then waits for the scan status P-variable to go to 1.
The ``complete`` method instead monitors the scan status variable and waits for it to go back to 0.


In the event of an aborted data collection, an additional Triggerable signal has been added to the PMAC device to be able to reset the PMAC.
The abort plan for FT will call:

.. code:: python

   yield from bps.trigger(pmac.abort_program)


which first sends a ``A`` command to the PMAC to tell it to abort the motion program being currently run and then resets the ``P2041`` variable to 0.
There is no need to reset the ``P2402`` variable as it's automatically reset once the new motion program starts.



Laser control
-------------

The ``laser_control`` plan switches a laser on and off by sending PMAC_STRINGS that set a pair of M-variables.
M-variables point to a location in memory and are usually used for user access or I/O operations - in this case they have to do with position compare settings.

The M-variables used here are M712/M711 for laser1 and M812/M811 for laser2.
M711 and M811 are set to 1, while and the value set to M712/M812 indicates when the triggering happens, eg:

::

   M712 = 0 if triggering on the falling edge -> laser off
   M712 = 1 if triggering on the rising edge -> laser on
