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

When running chip collections, the stage motors are moved via the `PMAC
device <https://github.com/DiamondLightSource/dodal/blob/main/src/dodal/devices/i24/pmac.py>`__
in a couple of different ways.

1. In most cases, the {x,y,z} motors are moved by sending a command to
   the PMAC as a ``PMAC_STRING``.

   -  Using a JOG command ``J:{const}``, to jog the motor a specified
      distance from the current position. For example, this will move
      motor Y by 10 motor steps:
      ``python      yield from bps.abs_set(pmac.pmac_string, "#2J:10")``

   -  The ``hmz`` strings are homing commands which will reset the
      encoders counts to 0 for the axis. All three motors are homed by
      sending the string: ``#1hmz#2hmz#3hmz``. In the plans this is done
      by triggering the home move:
      ``python       yield from bps.trigger(pmac.home)``

   -  Another pmac_string that can start a move has the format
      ``!x..y..``. This is a command designed to blend any ongoing move
      into a new position. A common one through the serial collection
      code is ``!x0y0z0``, which will start a move to 0 for all motors.
      ``python      yield from bps.trigger(pmac.to_xyz_zero)``

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

* The motor directions are stored in ``src/mx_bluesky/i24/serial/parameters/fixed_target/cs/motor_directions.txt.`` The motor number multiplied by the motor direction should give the positive chip direction. 
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
