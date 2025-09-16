Get Started with mx-bluesky
---------------------------
=======================
Development Environment
=======================

1. Clone this repo using SSH: ``git clone git@github.com:DiamondLightSource/mx-bluesky.git``
2. At the same directory level as you completed step 1

The recommended IDE is vscode, and a workspace which includes dodal has been set up in the repo. This can be used on a DLS machine as follows:

.. code-block:: bash

    cd /path/to/mx-bluesky  
    module load vscode  
    code ./.vscode/mx-bluesky.code-workspace  

- If you use vs code, you may need to set the python interpreter for both repositories to the one from the virtual environment created in ``.venv``

=========================
Supported Python versions
=========================

As a standard for the python versions to support, we are using the `numpy deprecation policy <https://numpy.org/neps/nep-0029-deprecation_policy.html>`_. 

Currently supported versions are: 3.10, 3.11.
