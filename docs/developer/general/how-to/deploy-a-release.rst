Deploy a New Release
====================

**Remember to discuss any new deployments with the appropriate beamline scientist.**


General deployment
--------------------

The ``utility_scripts/deploy/deploy_mxbluesky.py`` script will deploy the latest mx-bluesky version to a specified beamline. Deployments live in ``/dls_sw/ixx/software/bluesky/mx-bluesky_vX.X.X``. To do a new deployment you should run the deploy script from your mx-bluesky dev environment with e.g.

.. code:: console

    python ./utility_scripts/deploy/deploy_mxbluesky.py --beamline i24


If you want to test the script you can run:

.. code:: console

    python ./deploy/deploy_mxbluesky.py --dev-path /your-path/

and a released version will be put in ``/your-path/mxbluesky_release_test``.

If you need a specific beamline test deployment you can also run:


.. code:: console

    python ./deploy/deploy_mxbluesky.py --beamline i24 --dev-path /your-path/

which will create the beamline deployment (eg. I24) in the specified test directory ``/your-path/mxbluesky_release_test``.


**Note:** When deploying on I24, the edm screens for serial crystallography will be deployed automatically along with the mx-bluesky release. 
When running a ``dev`` deployment instead, `this script <https://github.com/DiamondLightSource/mx-bluesky/wiki/Serial-Crystallography-on-I24#deploying-a-local-version-of-the-edm-screens>`_ will also need to be run to get the latest version of the screens.


Hyperion deployment
-------------------

The ``utility_scripts/deploy/deploy_hyperion.py`` script will deploy the latest mx-bluesky/Hyperion version to a specified beamline. Deployments live in ``/dls_sw/ixx/software/bluesky/mx-bluesky_vX.X.X``.

If you have just created a release as above, you may need to run git fetch --tags to get the newest release.

To do a new deployment you should run the deploy script from your Hyperion dev environment with e.g.

.. code:: console

    python ./utility_scripts/deploy/deploy_hyperion.py i03


If you want to test the script you can run:


.. code:: console

    python ./utility_scripts/deploy/deploy_hyperion.py dev


and a released version will be put in ``/scratch/30day_tmp/hyperion_release_test``.

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
