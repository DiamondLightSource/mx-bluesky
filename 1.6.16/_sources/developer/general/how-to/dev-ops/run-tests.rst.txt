Run the tests using pytest
==========================

Testing is done with pytest_. It will find functions in the project that `look
like tests`_, and run them to check for errors. You can run it with::

    $ tox -e tests

When the tests are run in GitHub CI it will also report coverage to ``codecov.io``.

.. _pytest: https://pytest.org/
.. _look like tests: https://docs.pytest.org/explanation/goodpractices.html#test-discovery
