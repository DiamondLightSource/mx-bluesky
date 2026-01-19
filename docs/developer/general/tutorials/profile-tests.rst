Unit test performance
=====================

Ideally we want to keep the run-time of the unit tests down so that they are quick for developers to run locally. 
Preferably they should run in under a minute.

General Guidelines
------------------

Where a unit test waits for some event to happen, ``wait`` on the group to complete rather than adding a fixed 
``sleep``.

If testing a timeout, ensure that the timeout constant is either configurable or appropriately ``patch`` ed to a short 
value e.g. 
0.1s

How to profile the unit tests
-----------------------------

Sometimes tests can exhibit slowdowns for unknown reasons, in order to diagnose the cause it can be useful to profile
the test code.

The simplest way to find slow tests is to run ``pytest`` with the ``--durations`` option in order to find the slowest
tests.

e.g.

.. code-block:: bash

    pytest -m "not dlstbx" --durations=10

in order to find the top 10 slowest tests

You can then often step through in the debugger to find lines which execute slowly.


More detailed profiling
------------------------

Occasionally this is not sufficient. In which case more detailed profiling is necessary

Generating profiler output
--------------------------

You can install ``pytest-profiling`` to run the tests and generate profiling output

e.g.

.. code-block:: bash

    pip install pytest-profiling
    pytest --profile tests/unit_tests/hyperion/external_interaction/test_write_rotation_nexus.py::test_given_detector_bit_depth_changes_then_vds_datatype_as_expected


The output of this is quite brief but it will generate more detailed ``.prof`` files in the ``prof`` directory

To browse these files you need something useful. Snakeviz is a tool that can be used to browse the output:

.. code-block:: bash

    cd prof
    pip install snakeviz
    snakeviz combined.prof

An alternative tool is py-spy.

e.g.

.. code-block:: bash

    pip install py-spy
    py-spy record -o profile.svg -- pytest -s tests/unit_tests/hyperion/experiment_plans/test_robot_load_then_centre.py::test_given_no_energy_supplied_when_robot_load_then_centre_current_energy_set_on_eiger

This will generator an interactive SVG flamechart that can be opened in a browser to see hot methods.

Alternatively something like

.. code-block:: bash

    py-spy top -- pytest -s tests/unit_tests/hyperion/experiment_plans/test_robot_load_then_centre.py::test_given_no_energy_supplied_when_robot_load_then_centre_current_energy_set_on_eiger

to view a ``top`` -like updating view of where time is being spent. You will probably need to temporarily annotate the 
test with
``@pytest.mark.parametrize`` in order to make the tests loop sufficient times in order to observe.
