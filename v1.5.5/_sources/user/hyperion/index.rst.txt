Hyperion User Guide
===================

The Hyperion User Guide describes how to run, configure and troubleshoot Hyperion. For installation instructions, see
the Developer Guide.

What is Hyperion?
-----------------

Hyperion is a service for running high throughput unattended data collection (UDC). It does not provide a user 
interface, instead instructions are pulled from Agamemnon which is controlled by information obtained in ISPyB.

The software supports two modes of operation:

* UDC mode (experimental) where Hyperion automatically fetches instructions from Agamemnon.
* GDA mode (where GDA fetches and decodes the Agamemnon
  instructions). GDA mode will be removed in a future release.

The mode of operation is determined by configuration using the ``gda.mx.udc.hyperion.enable`` parameter


.. toctree::
    :caption: Topics
    :maxdepth: 1
    :glob:

    *
