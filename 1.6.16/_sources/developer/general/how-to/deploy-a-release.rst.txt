Deploy a New Release
====================

.. warning::

   This guide is for pre-containerised deployments. To see how deployments work using BlueAPI with kubernetes, please see `the updated guide <setup-blueapi-for-mx.html>`_.

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
