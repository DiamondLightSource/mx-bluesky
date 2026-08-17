Hyperion Baton
==============

The Hyperion baton is controlled by two PVs; these are described under `Special PVs`_

An approximate outline of how the various baton workflows operates is outlined in the flowcharts below:

.. image:: ../../../images/417717258-afbd813c-8941-445c-9fdf-255c167453cf.png

.. _Special PVs: ../../../user/hyperion/pvs.html


GDA-side Baton Integration
--------------------------

Below is a diagram showing how baton-handling in GDA integrates the GDA baton with the Hyperion Baton PV, using the 
``HyperionUDCRunner``.

The diagram represents an interim stage; at some point ``GDAUDCRunner`` can be eliminated and the baton management 
simplified.

.. uml:: gda-baton.puml
