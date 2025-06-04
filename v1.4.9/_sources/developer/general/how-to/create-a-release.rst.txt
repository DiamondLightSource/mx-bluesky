Create a New Release
-----------------------
===========
Pre-release
===========
Make sure that dodal has an up-to-date release. If not, create one (see `dodal release instructions <https://diamondlightsource.github.io/dodal/main/developer/how-to/make-release.html>`_).

=======
Release
=======

1. Create a new branch from main named pre followed by the release version e.g. pre_v0.1.0. The release versions should look like ``v{major}.{minor}.{patch}``.
2. On this branch pin the up-to-date version of dodal and the latest release of nexgen if necessary.
3. Go `here <https://github.com/DiamondLightSource/mx-bluesky/releases/new>`_.
4. Select Choose a new tag and type the version of the release, then select the branch created in step 1 as the target.
5. Click on Generate release notes. This will create a starting set of release notes based on PR titles since the last release.
6. You should now manually go through each line on the release notes and read it from the perspective of a beamline scientist. It should be clear from each what the change means to the beamline and should have links to easily find further info.
7. Publish the release

------------------------
Deciding release numbers
------------------------

Releases should obviously be versioned higher than the previous latest release. Otherwise you should follow this guide:

* Major - Changes that will break compatibility old functionality, large code rewrites
* Minor - New features
* Patch - Bug fixes
