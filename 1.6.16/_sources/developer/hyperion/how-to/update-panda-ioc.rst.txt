Update the PandA IOC
=====================

The IOC for the PandA can sometimes get out of sync with the production version of Ophyd-Async. Here is how to update it

Check if the IOC needs updating
""""""""""""""""""""""""""""""""

- Check the minimum panda IOC version required in the version of ophyd-async used in Hyperion's release version. This can be found in the ``MINIMUM_PANDA_IOC`` constant in `_hdf_panda.py <https://github.com/bluesky/ophyd-async/blob/main/src/ophyd_async/fastcs/panda/_hdf_panda.py>`_

- In a terminal:

.. code-block:: bash

    cd /dls_sw/work/R3.14.12.7/ioc/BL03I/BL03I-PY-IOC-02
    source venv/bin/activate
    pip freeze | grep pandablocks-ioc

Note that the IOC location will soon be moving to ``prod`` instead of ``work``.

- Compare the version from step one

Updating the IOC
""""""""""""""""""""""""""

- Update the Python IOC repo in the venv:

.. code-block:: bash

    cd /dls_sw/work/R3.14.12.7/ioc/BL03I/BL03I-PY-IOC-02
    source venv/bin/activate
    pip install --upgrade pandablocks-ioc=={desired version}


- After making sure the beamline isn't in use, restart the IOC:

.. code-block:: bash

    module load controls-tools

    console BL03I-PY-IOC-02

- Press ``ctrl+x``
- Disconnect by pressing ``ctrl+e``, then press ``c``, then press ``.``
