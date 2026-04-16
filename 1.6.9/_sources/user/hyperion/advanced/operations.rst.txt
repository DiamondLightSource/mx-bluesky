Overview of the Data Collection Plan
====================================

This page shows a high level overview of the overall data collection plan, called ``load_centre_collect``.

The intention of this is to show the sequencing of operations, including those operations that happen concurrently.

This has been broken down into three main diagrams 

- robot load and centring
- rotations
- changing energy

At a high level ``load_centre_collect`` performs all three operations, however depending on the requested collection 
parameters and whether the correct pin is already loaded, it may skip some of these steps.

Note that not all of the operations are shown, in order to reduce the complexity of the diagrams, and some of the 
steps have been slightly simplified.

In conjunction with the `Code Map`_ this should provide a good overview of operations that may assist in interpreting
logging output should any issues occur.


.. _`Code Map`: ../../../developer/code-map/index.rst

Robot Load and X-ray Centring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This shows

- Robot Load
- Pin Tip Detection
- Grid Detection
- X-ray Centring

.. uml:: concurrent_operations.puml

Rotations
~~~~~~~~~

.. uml:: concurrent_operations_rotation.puml

Set energy
~~~~~~~~~~

.. uml:: concurrent_operations_set_energy.puml
