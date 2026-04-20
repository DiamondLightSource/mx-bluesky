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
