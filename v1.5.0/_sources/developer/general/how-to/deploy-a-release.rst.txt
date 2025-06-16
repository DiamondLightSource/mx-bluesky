Deploy a New Release
====================

**Remember to discuss any new deployments with the appropriate beamline scientist.**

The ``utility_scripts/deploy/deploy_mx_bluesky.py`` script will deploy the latest mx-bluesky version to a specified beamline. Deployments live in ``/dls_sw/ixx/software/bluesky/mx-bluesky_vX.X.X``. To do a new deployment you should run the deploy script from your mx-bluesky dev environment with e.g.
If you have just created a new release, you may need to run git fetch --tags to get the newest release.

.. code:: console

    python ./utility_scripts/deploy/deploy_mx_bluesky.py i24


If you want to test the script for a specific beamline you can run:

.. code:: console

    python ./deploy/deploy_mx_bluesky.py i03 --dev


which will create the beamline deployment of the new release in ``/scratch/30day_tmp/mx-bluesky_release_test``.


.. note::

    When deploying on I24, the edm screens for serial crystallography will be deployed automatically along with the mx-bluesky release.


The script has a few additional optional arguments, which can be viewed with:

.. code:: console

    python ./deploy/deploy_mx_bluesky.py -h


For building and deploying a Docker image please see :doc:`../../hyperion/deploying-hyperion`.


.. note::

    On i03 the installation will succeed with error messages due to RedHat7 versions of a dependency being unavailable.
    This results in the installation being incomplete, thus requiring the following post-installation steps:

    First, on a RedHat8 workstation, run

    .. code:: console

        . ./.venv/bin/activate
        pip install confluent-kafka

    Then, on the control machine, run

    .. code:: console

        . ./.venv/bin/activate
        pip install -e .
        pip install -e ../dodal
