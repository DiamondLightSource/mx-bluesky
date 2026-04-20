Run linting using pre-commit
============================

Code linting is handled by ruff_, run under pre-commit_.

Running pre-commit
------------------

You can run the above checks on all files with this command::

    $ tox -e pre-commit

Or you can install a pre-commit hook that will run each time you do a ``git
commit`` on just the files that have changed::

    $ pre-commit install

Fixing issues
-------------

If ruff reports an issue you can attempt to automatically reformat all the files in the
repository::

    $ ruff check --fix .

If you get any ruff issues you will have to fix those manually.

VSCode support
--------------

The ``.vscode/settings.json`` will run linters and formatters 
on save. Issues will be highlighted in the editor window.
