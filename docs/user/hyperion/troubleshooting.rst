Troubleshooting
===============

.. contents::

Logging
-------

Hyperion logs to a number of different locations. The sections below describe the locations that are configured via 
environment variables for a standard server install; for kubernetes deployments please check the deployment 
``values.yaml`` for the configured locations. 

Graylog
~~~~~~~

Graylog is the recommended way to view logs. It is used for more centralised logging which is also more easily 
searched and archived. Log messages are sent to the `Hyperion graylog stream <https://graylog.diamond.ac.uk/streams/66264f5519ccca6d1c9e4e03/search>`_.


Startup Log
~~~~~~~~~~~

When ``hyperion_restart()`` is called by GDA, it will log the initial console output to a log file. This log file 
location is 
controlled by the ``gda.logs.dir`` property and is typically ``/dls_sw/<beamline>/logs/bluesky``.

On kubernetes deployments, the initial startup is sent to standard IO and is captured as part of the standard 
kubernetes logging facility.

Log files
~~~~~~~~~

By default, Hyperion logs to the filesystem.

The log file location is controlled by the ``LOG_DIR`` environment value. Typically this can be found in 
``/dls_sw/<beamline>/logs/bluesky``

Debug Log
~~~~~~~~~

The standard logs files do not record all messages, only those at INFO level or higher, in order to keep storage 
requirements to a minimum. 
In the event of an error occurring, then trace-level logging for the most recent events (by default 5000) is flushed 
to a separate set of log files. Due to the size of these files, they are stored separately from the main log files
. These logs are located in ``/dls/tmp/<beamline>/logs/bluesky`` by default, or 
otherwise as specified by the ``DEBUG_LOG_DIR`` environment variable. 

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

If Hyperion is deployed on Kubernetes then it can be managed from the beamline kubernetes dashboard, e.g. 
https://k8s-i03-dashboard.diamond.ac.uk

In the beamline namespace there will be a deployment ``hyperion-deployment``, a ``hyperion-svc`` service and associated 
pods, ingress etc. through which the current state may be observed / managed.
