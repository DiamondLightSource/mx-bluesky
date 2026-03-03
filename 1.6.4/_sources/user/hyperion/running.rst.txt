Running Hyperion
----------------

When installed, Hyperion should be running automatically. 

Restarting Hyperion
-------------------

If Hyperion is running as a standalone server installation, it can be (re)started from GDA by 
invoking ``hyperion_restart()`` from the Jython console.

If Hyperion is running in a Kubernetes container, then it can be restarted by scaling the deployment or 
deleting the pod (which will cause a new instance to be created)
