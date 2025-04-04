mx-bluesky
===========================

|ci| |coverage| |pypi_version| |license|

Contains code for working with Bluesky on MX beamlines at Diamond

============== ==============================================================
PyPI           ``pip install mx-bluesky``
Source code    https://github.com/DiamondLightSource/mx-bluesky
Documentation  https://DiamondLightSource.github.io/mx-bluesky
Releases       https://github.com/DiamondLightSource/mx-bluesky/releases
============== ==============================================================

Getting Started
===============

To get started with developing this repo at DLS run ``./utility_scripts/dls_dev_env.sh``.

If you want to develop interactively at the beamline we recommend using jupyter notebooks. You can get started with this by running::

    $ ./start_jupyter.sh

If you're doing more in-depth development we recommend developing with VSCode. You can do this at DLS by running::

    $ module load vscode
    $ code .vscode/mx-bluesky.code-workspace

.. |ci| image:: https://github.com/DiamondLightSource/mx-bluesky/actions/workflows/ci.yml/badge.svg?branch=main
    :target: https://github.com/DiamondLightSource/mx-bluesky/actions/workflows/ci.yml
    :alt: Code CI

.. |coverage| image:: https://codecov.io/gh/DiamondLightSource/mx-bluesky/branch/main/graph/badge.svg
    :target: https://codecov.io/gh/DiamondLightSource/mx-bluesky
    :alt: Test Coverage

.. |pypi_version| image:: https://img.shields.io/pypi/v/mx-bluesky.svg
    :target: https://pypi.org/project/mx-bluesky
    :alt: Latest PyPI version

.. |license| image:: https://img.shields.io/badge/License-Apache%202.0-blue.svg
    :target: https://opensource.org/licenses/Apache-2.0
    :alt: Apache License

..
    Anything below this line is used when viewing README.rst and will be replaced
    when included in index.rst

See https://DiamondLightSource.github.io/mx-bluesky for more detailed documentation.
