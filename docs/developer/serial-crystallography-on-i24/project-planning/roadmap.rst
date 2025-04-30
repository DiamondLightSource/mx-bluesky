Roadmap
-------

For a closer look at the ongoing work: `I24ssx
board <https://github.com/orgs/DiamondLightSource/projects/10/views/2>`__

Ongoing list of TODOs (Updated 04/2025)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Bluesky**:

1. Set up blueapi and run mx-bluesky on the beamline kubernetes cluster. I24 should be due to get one in shutdown 4 2024.

2. Improve/fix the issues with the PMAC ProgramRunner: it should monitor the counter PV as well as the status PV.

3. Use callbacks for file IO, eg. to write parameter and map files, nexus writer and ispyb deposition.

   - Improve nexgen-server use

4. Convert detector set up to use bluesky plans and ophyd_async devices.

   - Eiger device in dodal needs to be converted to ophyd_async and updated to work with different Eigers on several beamlines. This work is dependent on other work out of the scope of this project, see `Dodal#700 <https://github.com/DiamondLightSource/dodal/issues/700>`__ and linked issues.
   - Update JF code for serial, move devices into dodal and merge it.
   - Investigate using the existing Pilatus in ophyd_async which writes HDF5 instead of CBFs, but we may want to make a CBF-writing Pilatus. However, the Pilatus detector is due to be removed soon.

5. Start integrating Panda, at least for fixed-target collections.

6. Implementation of serial tools to be used at XFELS.

   - Reinstate removed code from sacla and move it to bluesky.
   - Add any plans/devices that might be needed for other locations.

7. Reinstate full mapping code using bluesky.

**React UI**:

1. Prepare generic react components to match the features in the edms.

   - Components for things currently managed by general purpose PVs (eg. mapping, pump probe).
   - Set up collection parameters
   - Move hardware: eg. detector stage
   - Monitor beamline state
2. Move the moveonclick to the wbe UI

   - Component for the OAV viewer on the UI.
   - Components to set the zoom and move the backlight using bluesky plans.
   - Look into drawing the crosshair in epics.
   - Refactor moveonclick code.



.. list-table:: Rough Roadmap
   :widths: 30 30 15
   :header-rows: 1

   * - Work Ongoing
     - Rough Timeline
     - Completed
   * - PMAC ProgramRunner updates/fixes
     - Apr. 24
     - :material-regular:`pending;2em`
   * - Update/improve coordinate system maker on the PMAC
     - Apr. /May 25
     - :material-regular:`pending;2em`
   * - Convert the current detector set up code to bluesky plans using the device
     - Dependent on `FastCS Eiger issues <https://github.com/bluesky/ophyd-async/issues?q=is%3Aissue+is%3Aopen+eiger>`__ being completed
     - :material-regular:`pending;2em`
   * - Set up callback for nexus writing
     - Dec. 24
     - :material-regular:`pending;2em`
   * - Set up callback for ispyb deposition
     - Dec. 24
     - :material-regular:`pending;2em`
   * - Prepare first React components to switch from EDM to a web GUI
     - Dec. 24 / Jan. 25
     - :material-regular:`check;2em`
   * - Move the OAV viewer to a web GUI
     - May / Jun. 25
     - :material-regular:`pending;2em`
   * - Deploy a first basic version of the web UI
     - May 25
     - :material-regular:`pending;2em`
   * - Fully test extruder collections
     - Nov. 24
     - :material-regular:`check;2em`
   * - Fix permissions and allow for user collections
     - Dec. 24 / Jan. 25
     - :material-regular:`check;2em`
   * - Refactor logger
     - Nov. 24
     - :material-regular:`check;2em`
   * - Improve current alignment - use multiple zooms (moveonclick)
     - Nov. 24
     - :material-regular:`check;2em`
   * - Set up a PV backend, eg. ``pvws``, for web GUI on the beamline.
     - Jan. 25
     - :material-regular:`check;2em`


Experiment types required
=========================

-  Extruder

   -  Standard
   -  Pump probe

-  Fixed target (probably about 80-85% of serial on I24)

   -  Standard chip collection – option for multiple exposures in each
      spot
   -  Pump probe - see for short description
      https://confluence.diamond.ac.uk/display/MXTech/Dynamics+and+fixed+targets

      -  Short delays
      -  Excite and visit again
      -  Long delays with fast shutter opening/closing

-  (Future) Fixed target with rotation at each “window” (Preliminary
   work done by beamline staff on the PMAC program
   https://confluence.diamond.ac.uk/display/MXTech/Grids+with+rotations)

Details of zebra settings for each type:
https://confluence.diamond.ac.uk/display/MXTech/Zebra+settings+I24

Note that most of the set up for the fixed target is actually done internally
by the PMAC, via sending PMAC strings.



--------------

Old roadmap for reference


+---------------------------------------+----------------+---------------------------------+
|             Work Ongoing              | Rough Timeline |            Completed            |
+=======================================+================+=================================+
| Document how to set up the current    | Ongoing        | :material-regular:`check;2em`   |
| visit, deploy the edm screens and run |                |                                 |
| a simple collection                   |                |                                 |
+---------------------------------------+----------------+---------------------------------+
| Chip collections using bluesky        | Jan./Feb. 24   | :material-regular:`pending;2em` |
+---------------------------------------+----------------+---------------------------------+
| Extruder collections using bluesky    | Feb. 24        | :material-regular:`pending;2em` |
+---------------------------------------+----------------+---------------------------------+
| Create an Ophyd device for the        | Jan. 24        | :material-regular:`pending;2em` |
| Pilatus detector and use it, along    |                |                                 |
| with the Eiger device, to collect     |                |                                 |
| data                                  |                |                                 |
+---------------------------------------+----------------+---------------------------------+
| Start using Ophyd devices for the     | 15th Dec. 23   | :material-regular:`check;2em`   |
| set up tasks - eg. zebra              |                |                                 |
+---------------------------------------+----------------+---------------------------------+
| Use a plan to find the fiducials      | 15th Dec. 23   | :material-regular:`check;2em`   |
+---------------------------------------+----------------+---------------------------------+
| Create an Ophyd device for for the    | 1st Dec. 23    |                                 |
| pmac and use it to move the chip      |                | :material-regular:`check;2em`   |
| stages                                |                |                                 |
+---------------------------------------+----------------+---------------------------------+
| Set up a first bluesky plan to move   | 15th Nov. 23   |                                 |
| the detector stage and set up the     |                | :material-regular:`check;2em`   |
| detector in use                       |                |                                 |
+---------------------------------------+----------------+---------------------------------+
| Come up with a first parameter        | 1st Dec 23     |                                 |
| model                                 |                | :material-regular:`check;2em`   |
+---------------------------------------+----------------+---------------------------------+
| Start sending logs to graylog         | Nov. 23        | :material-regular:`check;2em`   |
+---------------------------------------+----------------+---------------------------------+
| Permissions issues - run as a service | Dec. 23        | :material-regular:`check;2em`   |
+---------------------------------------+----------------+---------------------------------+
| Deploy a first version of mx-bluesky  | Nov. 23        |                                 |
| with the current iteration - tested   |                | :material-regular:`check;2em`   |
| on the beamline - of the serial       |                |                                 |
| tools. Set up a ``module load`` that  |                |                                 |
| they can use it for ssx data          |                |                                 |
| collections.                          |                |                                 |
+---------------------------------------+----------------+---------------------------------+
| Generic deployment for edm screens    | Summer 23      | :material-regular:`check;2em`   |
+---------------------------------------+----------------+---------------------------------+
| Tidy up original code and add some    | Summer 23      | :material-regular:`check;2em`   |
| tests                                 |                |                                 |
+---------------------------------------+----------------+---------------------------------+
