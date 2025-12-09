Server Install
--------------

Install Location
~~~~~~~~~~~~~~~~

Hyperion is generally installed in the beamline software directory:

``/dls_sw/<beamline>/software/bluesky``

This directory contains versioned installation folders ``mx-bluesky_vx.y.z`` for each installed version. Within the 
directory there is a symlink ``hyperion`` to the currently active version. This is generally a symlink to either 
``hyperion_stable`` or ``hyperion_latest`` symlinks which then point to the latest stable and development releases 
respectively.

Switching Versions
~~~~~~~~~~~~~~~~~~

For example to switch from the development to the stable release simply:

::

    rm hyperion
    ln -s hyperion_latest hyperion

After this you will need to run ``hyperion_restart()`` in the GDA jython console to restart hyperion

Verifying that Hyperion is running
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To verify that the correct version of Hyperion is running, you should be able to view the process on the control 
server, ssh into the control server, the output of ``ps ax`` should be something like the following, showing which 
deployment is currently running. You should see two processes, the main process and also the external callback process. 

::

    $ ps ax | grep hyperion
    1181420 ?        Sl     2:36 /dls_sw/i03/software/bluesky/mx-bluesky_v1.5.0/mx-bluesky/.venv/bin/python /dls_sw/i03/software/bluesky/mx-bluesky_v1.5.0/mx-bluesky/.venv/bin/hyperion
    1181422 ?        Sl     1:54 /dls_sw/i03/software/bluesky/mx-bluesky_v1.5.0/mx-bluesky/.venv/bin/python /dls_sw/i03/software/bluesky/mx-bluesky_v1.5.0/mx-bluesky/.venv/bin/hyperion-callbacks

Kubernetes Install
------------------

If Hyperion is deployed on Kubernetes (currently experimental) then it can be managed from the beamline kubernetes 
dashboard, e.g. 
https://k8s-i03-dashboard.diamond.ac.uk

In the beamline namespace there will be a deployment ``hyperion-deployment``, a ``hyperion-svc`` service and associated 
pods, ingress etc. through which the current state may be observed / managed.

Logging
~~~~~~~

On kubernetes deployments, the initial startup is sent to standard IO and is captured as part of the standard 
kubernetes logging facility.

The configured logging locations are defined in the ``values.yaml`` for the specific deployment Helm chart. 
