Hyperion User Guide
===================

The Hyperion User Guide describes how to run, configure and troubleshoot Hyperion. For installation instructions, see
the Developer Guide.

What is Hyperion?
-----------------

Hyperion is a service for running high throughput unattended data collection (UDC). It does not provide a user 
interface, instead instructions are pulled from Agamemnon which is controlled by information obtained in ISPyB.

Running Hyperion
----------------

When installed, Hyperion should be running automatically. If it is not running, it can be (re)started from GDA by 
invoking ``hyperion_restart()`` from the Jython console.


.. toctree::
    :caption: Topics
    :maxdepth: 1
    :glob:

    *
