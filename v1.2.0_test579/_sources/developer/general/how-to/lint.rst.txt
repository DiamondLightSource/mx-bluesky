Run linting using pre-commit
============================

Code linting is handled by black_, ruff run under pre-commit_.

Running pre-commit
------------------

You can run the above checks on all files with this command::

    $ tox -e pre-commit

Or you can install a pre-commit hook that will run each time you do a ``git
commit`` on just the files that have changed::

    $ pre-commit install

Fixing issues
-------------

If black reports an issue you can tell it to reformat all the files in the
repository::

    $ black .

If you get any ruff issues you will have to fix those manually.

VSCode support
--------------

The ``.vscode/settings.json`` will run black and isort formatters as well as
flake8 checking on save. Issues will be highlighted in the editor window.
