Special PVs
-----------

Baton
~~~~~

In order to arbitrate access to the beamline between Hyperion and GDA there are two baton string PVs REQUESTED_USER and 
CURRENT_USER.

Hyperion will only start operating once REQUESTED_USER has been set to Hyperion, at which point it will set 
CURRENT_USER. To request the baton from Hyperion, set REQUESTED_USER to some other value, when Hyperion completes the
current action, it will relinquish CURRENT_USER.
