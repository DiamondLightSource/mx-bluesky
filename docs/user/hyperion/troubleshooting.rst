Troubleshooting
===============

.. contents::

Known Issues
------------

Odin Errors when there are filesystem issues
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

https://github.com/DiamondLightSource/mx-bluesky/issues/1199

On occasions where there are issues with the filesystem you may see errors similar to

::

    ophyd.utils.errors.UnknownStatusFailure: The status (Status(obj=EpicsSignalWithRBV
    (read_pv='BL03I-EA-EIGER-01:OD:Capture_RBV', name='eiger_odin_file_writer_capture', parent='eiger_odin_file_writer',
    value=0, timestamp=1754488753.208739, auto_monitor=False, string=False, write_pv='BL03I-EA-EIGER-01:OD:Capture',
    limits=False, put_complete=False), done=True, success=False) & SubscriptionStatus(device=eiger_odin_meta_ready,
    done=False, success=False)) has failed. To obtain more specific, helpful errors in the future, update the Device
    to use set_exception(...) instead of _finished(success=False).

hyperion_restart() sometimes times out
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes hyperion_restart() will time out waiting for Hyperion to start, in the Jython console you may see the 
following

::

    InteractiveConsole exception: hyperion_utils.exceptions.HyperionFailedException: Hyperion failed to start, see /dls_sw/i03/logs/bluesky/start_log.log for log
    org.python.core.PyException: hyperion_utils.exceptions.HyperionFailedException: Hyperion failed to start, see /dls_sw/i03/logs/bluesky/start_log.log for log
	at org.python.core.PyException.doRaise(PyException.java:239)
	at org.python.core.Py.makeException(Py.java:1654)
	at org.python.core.Py.makeException(Py.java:1658)
	at org.python.core.Py.makeException(Py.java:1662)

However on inspection the start log will not show any errors. Hyperion running can be verified as above `Verifying 
that Hyperion is running`_

.. _`Verifying that Hyperion is running`: advanced/install.rst

Smargon Motion
~~~~~~~~~~~~~~

There are potential race conditions surrounding smargon moves. This may manifest as a CancelledError or TimeoutError 
on one of the smargon axes. The workaround if this occurs is to run a collection in GDA to confirm correct operation 
and then return control to Hyperion. 

We believe this is fixed with https://github.com/DiamondLightSource/mx-bluesky/issues/1049 however it is possible 
that this may recur.
