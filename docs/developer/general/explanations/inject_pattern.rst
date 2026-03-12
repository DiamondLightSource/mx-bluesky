Device Injection in Plans
=========================

Bluesky plans are Python generator functions. When a plan needs a hardware device,
the natural approach would be to import a beamline singleton directly or accept it
as a required argument. Both have drawbacks:

- **Direct import** couples the plan to a specific beamline environment, making it
  untestable in isolation and non-portable.
- **Required argument** works for direct calls but breaks the blueapi dispatch model,
  which needs to instantiate plans from JSON parameters without the caller supplying
  device objects.

The ``inject()`` pattern solves this by declaring device dependencies as defaulted
parameters that a dispatch framework can resolve at runtime.

How It Works
------------

``inject()`` is defined in ``dodal.common.coordination``::

    def inject(name: str = "") -> Any:  # type: ignore
        return name

It returns the string it is given, but typed as ``Any``. This means:

- At **Python runtime**, the default value of the parameter is just the string
  ``"jungfrau"`` — a plain marker.
- At **type-check time**, ``Any`` satisfies any type annotation, so mypy/pyright
  accept ``jungfrau: Jungfrau = inject("jungfrau")`` without error.

A plan using this pattern looks like::

    from dodal.common import inject
    from dodal.devices.jungfrau import Jungfrau

    def do_pedestal_darks(
        exp_time_s: float = 0.001,
        jungfrau: Jungfrau = inject("jungfrau"),
    ) -> MsgGenerator:
        ...

Who Resolves the Injection
--------------------------

**blueapi** inspects the plan's function signature when it receives a dispatch
request. For any parameter whose default value is a string (as returned by
``inject()``), blueapi looks up a device with that name in its device context and
substitutes the real object before calling the plan.

The string passed to ``inject()`` must match the ``name`` attribute of the device
as registered in the blueapi context (which comes from the dodal beamline module).

**When calling a plan directly** (e.g. in a script or notebook), the injection
default is never used — you pass the device yourself::

    RE(do_pedestal_darks(exp_time_s=0.001, jungfrau=my_jungfrau_device))

Summary
-------

+---------------------------+------------------------------------------------------+
| At parse time             | ``inject("jungfrau")`` returns the string            |
|                           | ``"jungfrau"``, typed as ``Any``                     |
+---------------------------+------------------------------------------------------+
| At type-check time        | ``Any`` satisfies any annotation; no type error      |
+---------------------------+------------------------------------------------------+
| At runtime via blueapi    | blueapi reads the default string, looks up the       |
|                           | device by name in its context, injects the real      |
|                           | object                                               |
+---------------------------+------------------------------------------------------+
| At runtime (direct call)  | Caller passes the device explicitly; default is      |
|                           | never used                                           |
+---------------------------+------------------------------------------------------+

The name passed to ``inject()`` is a contract: it must match the device's
``.name`` as registered in the blueapi device context.
