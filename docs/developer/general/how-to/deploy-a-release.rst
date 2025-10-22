Deploy a New Release
====================

**Remember to discuss any new deployments with the appropriate beamline scientist.**

The ``utility_scripts/deploy/deploy_mx_bluesky.py`` script will deploy the latest mx-bluesky version to a specified beamline. Deployments live in ``/dls_sw/ixx/software/bluesky/mx-bluesky_X.X.X``. To do a new deployment you should run the deploy script from your mx-bluesky dev environment with e.g.
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

    On i03 the installation will succeed with error messages due to RedHat7 versions of dependencies being unavailable.
    This results in the installation being incomplete, thus requiring the following post-installation steps:

    First, on a RedHat8 workstation, run

    .. code:: console

        . ./.venv/bin/activate
        pip install confluent-kafka
        pip install contourpy

    Then, on the control machine, run

    .. code:: console

        . ./.venv/bin/activate
        pip install -e .
        pip install -e ../dodal

.. _deploying-to-i04-blueapi:

Deploying to I04 BlueAPI
------------------------

To deploy to I04 BlueAPI, update the Chart.yaml and values.yaml in the i04-services repository to match the release version. It's a good idea to bump BlueAPI to the latest version too.

Look at this `example <https://gitlab.diamond.ac.uk/controls/containers/beamline/i04-services/-/commit/f0ea7432ae996834001bbe50a07ba86d23534749>`_ as a guide. Note that mx-bluesky has recently dropped the ``v`` from it's version numbers.

Once this change has been merged into main and the CI has completed successfully, press synchronise on the I04 ArgoCD page. This will update the version deployed in Kubernetes.
