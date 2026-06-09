Debugging Hyperion in Kubernetes
================================

Attaching to kubernetes scratch in the PVC
------------------------------------------

Loading the scratch folder in visual studio is similar to how it is done for ``blueapi``.

You will need to have installed the Microsoft Kubernetes extension for VSCode. For details on how that is done, see `Debugging in the Cluster`_

Essentially the steps are:

.. code-block:: bash

    $ module load <cluster>
    $ echo $KUBECONFIG

In VSCode, run ``Kubernetes: Set Kubeconfig`` and copy the location of your kubeconfig printed from above.
Then from the Kubernetes plugin tray, expand Clusters -> <cluster> -> Workloads -> Pods -> ``hyperion-scratch``.
Right click -> Attach Visual Studio Code to attach to the scratch pod.
In the Explorer of the new VSCode window that opens, click Open Folder and enter ``/`` as the folder on the pod to open.

Select File->Open Workspace from File... and select ``/scratch/mx-bluesky/.vscode/hyperion-k8s-scratch.code-workspace``
You can now edit files on the scratch persistent volume located in /scratch.

When debugging inside the k8s pod, VSCode python extensions run remotely, so you will need to install them into the pod - open the extensions sidebar and install the various python extensions - these install a memory-hungry node server on the ``hyperion-scratch`` container.


.. _Debugging in the Cluster: https://diamondlightsource.github.io/python-copier-template/main/how-to/debug-in-cluster.html

Attaching a debugger
--------------------

The ``hyperion`` and ``hyperion-callbacks`` commands accept ``--debug-port`` and ``--wait-for-attach`` options.

``--debug-port`` enables remote debug using ``debugpy``. This is passed to ``hyperion`` and ``hyperion-callbacks`` if ``supervisor.enableDebugging`` is specified in ``values.yaml``, using the ``supervisor.debugPort`` value. Equivalent properties exist in ``values.yaml`` for the callbacks.
The default port numbers are 5050 and 5051.

If the pod is deployed with this option it will cause the container to listen on the port for VSCode to attach the debugger.
There is also a ``--wait-for-attach`` option available if you need this.

Having completed the steps above to attach to the PVC, when the pods are running in debug mode you can then run

.. code-block:: bash

   $ kubectl port-forward pod/<pod name> 5050:5050 -n <k8s namespace>

This will forward the port from the pod to your local machine.
There are launchers configured for the workspace in .vscode/launch.json, select either ``Attach to K8s Hyperion Supervisor`` or ``Attach to K8s Hyperion Callbacks`` to connect on 5050/5051 as appropriate, this will put you into debug mode.
