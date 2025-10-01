Hyperion User Guide
===================

The Hyperion User Guide describes how to run, configure and troubleshoot Hyperion. For installation instructions, see
the `Developer Guide`_.

What is Hyperion?
-----------------

Hyperion is a service for running high throughput unattended data collection (UDC). It does not provide a user 
interface, instead instructions are pulled from Agamemnon which is controlled by information obtained in ISPyB.

The software supports two modes of operation:

* UDC mode (experimental) where Hyperion automatically fetches instructions from Agamemnon.
* GDA mode (where GDA fetches and decodes the Agamemnon
  instructions). GDA mode will be removed in a future release.

The mode of operation is determined by configuration using the ``gda.mx.udc.hyperion.enable`` parameter inside 
GDA properties. See `configuration`_ for other properties that control Hyperions behavior. 

Once Hyperion has received a request, either from GDA or directly from Agamemnon, it will do the following tasks:

- Robot Load (if the requested sample has not yet been loaded)
- Pin tip centring using the OAV
- Xray Centring using 2 2D gridscans 
- A number of data collections, depending on the number of centres returned from Zocalo and the applied selection criteria

During this it will generate the following outputs:

- Snapshots on robot load, XRC and rotations
- Data collections in ISPyB for the gridscans and rotations as well as entries for robot load/unload
- NeXus files for each data collection
- Alert notifications on loading a new container and on beamline error conditions when intervention is required.  

To increase throughput, the behavior of Hyperion differs in many ways from UDC under GDA. The main ways this manifests 
to a user is:

- Xray Centring is 2 2D gridscans (rather than the one gridscan and one line scan in GDA). For speed, the eiger is only
  armed once for both of these and the data is split up after the fact. This means on the filesystem there is one set of 
  hdf files for both gridscans but two NeXus files. The two grid scans are stored in ISPyB under one data collection 
  group so at first glance it may look like one gridscan in synchweb but you can click through to see both scans.
- If an xray centre cannot be done on a pin (because it is too long/short or bent), or if no diffraction is found in the 
  xray centring data, the sample will be immediately unloaded without a rotation scan being done and the next sample loaded.

For a more detailed breakdown of the operation, it may be helpful to browse the  `Code Map`_

.. _Code Map: ../../developer/code-map 
.. _Developer Guide: ../../developer/hyperion/deploying-hyperion
.. _configuration: ./configuration

.. toctree::
    :caption: Topics
    :maxdepth: 1
    :glob:

    *
