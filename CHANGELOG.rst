duiker change log
=================

Unreleased
----------

Added
~~~~~

* Added `head` and `tail` commands to show first or last *N* commands.
* Added `sqlite3` (`sql`, `shell`) command to open database in SQLite3 shell.

Fixed
~~~~~

* (`#1`_) Check that Python can interpret ``HISTTIMEFORMAT``.
* Do not assume ``HISTTIMEFORMAT`` evaluates to a fixed-length string.

.. _#1: https://github.com/benwebber/duiker/issues/1
