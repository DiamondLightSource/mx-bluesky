2. mx-bluesky repository structure
==================================

Date: 2024-08-21

Status
------

Accepted

Context
-------

Initially, we wanted to separate "application code" such as hyperion from "library code" generic over MX beamlines belonging in ``mx-bluesky``. 
However, as these were developed together and also together with ``dodal``, dependency management became impossible.

Decision
--------

We will stick to a monorepo repository structure as follows:

.. code-block:: text

    mx_bluesky/
    ├-src/
    | └-mx_bluesky/
    |   ├-common/               # Plan stubs, utilities, and other common code
    |   ├-beamlines/
    |   | ├-i03/
    |   | ├-i04/
    |   | └-i24/
    |   |   └-serial/           # Plans for one beamline go in the respective module
    |   └-hyperion/             # Plans for more than one beamline go in the top level
    ├-tests/
    | ├-unit_tests/                             # Tests are separated into "unit_tests" and "system_tests"
    | | └-{mirror of mx_bluesky structure}/     # Where the former refers to tests which can be run without
    | ├-system_tests/                           # access to external services, and the latter might need
    | | └-{mirror of mx_bluesky structure}/     # to talk to ISPyB, the DLS filesystem, etc.
    | └-test_data/
    └-docs/
      ├-developer/
      └-user/

To preserve some of the benefits we would have had from separate repositories, code from beamline or "application" 
modules (e.g. ``mx_bluesky.i24.serial`` or ``mx_bluesky.hyperion``) may import from ``mx_bluesky.common`` but not 
the other way around - this should be enforced with a check in CI.
