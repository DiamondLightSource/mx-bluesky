System Tests
============

The system tests are run by a project hosted in a GitLab private repository, `Hyperion System Testing`_.

This contains a ``.gitlab-ci`` pipeline that defines a job that runs the tests.
 
System Test Images
------------------

The system tests require a number of container images to run:

   * The test runner image
   * An ISPyB MariaDB database server image
   * An ExpEye image

It is expected that these images should need to change only infrequently and builds are triggered
manually as needed - see the Hyperion System Testing project for how to rebuild them and how to trigger the tests. 

.. _`Hyperion System Testing`: https://gitlab.diamond.ac.uk/MX-GDA/hyperion-system-testing
