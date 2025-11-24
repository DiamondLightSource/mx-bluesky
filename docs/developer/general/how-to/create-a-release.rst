Create a New Release
-----------------------
===========
Pre-release
===========
Make sure that dodal has an up-to-date release. If not, create one (see `dodal release instructions <https://diamondlightsource.github.io/dodal/main/developer/how-to/make-release.html>`_).

=======
Release
=======

1. Create a new branch from main named pre followed by the release version e.g. pre_0.1.0. The release versions should look like ``{major}.{minor}.{patch}``.
2. On this branch pin the latest release of dodal, and nexgen if necessary, then push to GitHub. (e.g "dls-dodal == 1.63.0")
3. Make sure the CI is passing for this new pre-release branch.
4. Go `here <https://github.com/DiamondLightSource/mx-bluesky/releases/new>`_.
5. Select Choose a new tag and type the version of the release, then select the branch created in step 1 as the target.
6. Click on Generate release notes. This will create a starting set of release notes based on PR titles since the last release.
7. You should now manually go through each line on the release notes and read it from the perspective of a beamline scientist. It should be clear from each what the change means to the beamline and should have links to easily find further info.
8. Publish the release

NOTE FOR USING THE MX-BLUESKY-BLUEAPI IMAGE: If using this image with BlueAPI's helmchart for deployment, the version of dodal which is installed will be the version which is pinned in the BlueAPI, rather than what's in mx-bluesky's pyproject.toml. Before releasing, you should pin BlueAPI to a version which uses a dodal version which is compatible with itself AND mx-bluesky. The deployment will fail if BlueAPI has no version which works with the desired dodal version
Follow these :ref:`instructions <deploying-to-i04-blueapi>` on how to deploy to I04 BlueAPI.

------------------------
Deciding release numbers
------------------------

Releases should obviously be versioned higher than the previous latest release. Otherwise you should follow this guide:

* Major - Changes that will break compatibility old functionality, large code rewrites
* Minor - New features
* Patch - Bug fixes
