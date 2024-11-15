Beamline Energy Implementation
==================================

Currently beamline energy is controlled in GDA from within ``beamlineSpecificEnergy.py``

There is a class ``beamLineSpecificEnergy`` which inherits from ``beamLineEnergy``

To do the alignment there are two implementations ``AutomatedAlign`` and ``QuickAlign``

in beamLineEnergy it basically does the equivalent of

.. code::

   def align_beam(self, quick_align): # Re-align button
      if quick_align:
         self.QuickAlign()
      else:
         self.energyController.moveTo(self.getPosition())
         self.align_beam_worker()

* The entry point for setting the energy is in ``beamLineEnergy.asynchronousMoveTo`` which overrides the asynchronousMoveTo in Scannable. ScannableMotionBase delegates moveTo to the async version.

* ``asynchronousMoveTo`` ultimately calls ``asynchronousMoveTo_worker`` in ``beamLineSpecificEnergy``

- ``asynchronousMoveTo_worker`` performs a number of operations all on separate threads and then waits for them to finish 
   - ``asynchronousMoveTo_worker`` creates a ``MoveVfmThread`` instance, which initialises ``VFM_X`` and ``VFM_Y`` stripe according to both the current and requested energy.
   - ``asynchronouseMoveTo_workersets`` the focus mode Not sure if we need to implement this 
   -  ``asynchronouseMoveTo_workersets`` detector energy Don't think we need to do this 
   -  asynchronouseMoveTo_workersets energy in ``ChangeEnergyThread``, this is where it sets ``BeamLineEnergy_Bragg_eV`` and then calls ``energyController.moveTo()``
   - ``asynchronouseMoveTo_worker`` calls ``mirrorFocus.check_voltages()`` (when and if depends on factors)
   -  ``asynchronouseMoveTo_worker`` calls ``align_beam_worker()`` in the superclass which delegates to ``align_beam_specific_worker()``
   - ``asynchronouseMoveTo_worker`` keeps all its async threads tracked in energy_threads array and waits for them to complete at the end of the func

align_beam_specific_worker()
----------------------------

* Open the experiment shutter
* Read initial state (Think this is what setParameters does)
* close camera shutter
* set attenuator transmission
* disable feedback loop
* set roll converter to target value
- If full XBPM feedback
   - find peak gaussian strategy #1
- else
   - find peak gaussian strategy #2
* set slit size
* reset attenuation
* reenable feedback loop
``AutomatedAlign``
* is referenced by ``HandleCollectRequests`` in ``do_automated_align()`` but the latter appears to be unused
``QuickAlign``
* not referenced by anything but is probably a manual entry point
