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

Once Hyperion has received a request, either from GDA or directly from Agamemnon, it will do the following tasks:

- Robot Load (if necessary)
- Pin tip detection using the OAV
- Xray Centring
- A number of data collections, depending on the number of centres returned from Zocalo and the applied selection criteria

During this it will generate the following outputs:

- Snapshots on robot load, XRC and rotations
- Data collections in ISPyB for the gridscans and rotations as well as entries for robot load/unload
- Nexus files for each data collection
- Alert notifications on loading a new container and on beamline error conditions when intervention is required.  

For a more detailed breakdown of the operation, it may be helpful to browse the  `Code Map`_

.. _Code Map: ../../developer/code-map 

.. toctree::
    :caption: Topics
    :maxdepth: 1
    :glob:

    *
