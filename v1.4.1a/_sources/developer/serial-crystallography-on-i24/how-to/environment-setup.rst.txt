Set up for serial experiments on I24
------------------------------------------------------------------------

To set up an enviroment to run the serial crystallography collection scripts,
please follow the instructions in :doc:`../../general/how-to/get-started`. 
Once this is done, the environment can be started by running:

.. code:: bash

   cd /path/to/mx-bluesky
   source .venv/bin/activate

On beamline I24, the package will be saved in
``/dls_sw/i24/software/bluesky``.

Deploying a local version of the EDM screens
============================================

Every time a change is made to the template EDM screens saved in the
repo, a new set should be deployed to the beamline ot to the ``dev``
environment to get the update. The ``deploy_edm_for_ssx.sh`` will create
a local copy of the all EDM screens - both for a fixed target and for a
serial jet collection - in a ``edm_serial/`` directory with all the
shell commands pointing to the correct scripts/edm locations.

.. code:: bash

   ./path/to/mx-bluesky/utility_scripts/deploy/deploy_edm_for_ssx.sh

Setting the current visit directory
===================================

A new visit directory might need to be set before every user or
commissioning beamtime. This can be done by a member of the beamline
staff by modifying the file ``/dls_sw/i24/etc/ssx_current_visit.txt`` to
point to the current visit and then running the command:

.. code:: bash

   ./path/to/mx-bluesky/src/mx_bluesky/beamlines/i24/serial/set_visit_directory.sh

Note that the default experiment type for the script setting the
directory will be ``fixed-target``. In case of an extruder collection,
to set the correct visit PV the experiment type should be modified from
the command line.

.. code:: bash

   ./path/to/mx-bluesky/src/mx_bluesky/beamlines/i24/serial/set_visit_directory.sh extruder
