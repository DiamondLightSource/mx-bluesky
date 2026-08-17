3. Python version support
=========================

Date: 2024-08-22

Status
------

Accepted

Context
-------

We need to decide which versions of python we will support. We want to be able to make use of new python features,
and reduce the number of different supported versions, but we also want scientists in a variety of environments to
be able to use the code in this repository. At the time of writing this, we merged https://github.com/DiamondLightSource/hyperion
into this repository. It only supported python 3.11, while ``mx-bluesky`` at this time supported 3.10 and 3.11.

Decision
--------

We will support no older python version than described in https://numpy.org/neps/nep-0029-deprecation_policy.html
We may if appropriate choose to drop python versions before they are dropped by that schedule. Instead
of modifying ``hyperion`` to work with python 3.10, we are dropping support for it at the time of writing this.

Consequences
------------

We must always support at least the newest major python version, and most likely several versions behind it, but no version older than 42 months.
