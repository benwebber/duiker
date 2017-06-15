duiker change log
=================

0.2.0
-----

Added
~~~~~

* Added `head` and `tail` commands to show first or last *N* commands.
* Added `sqlite3` (`sql`, `shell`) command to open database in SQLite3 shell.

Changed
~~~~~~~

* Rewrote Duiker in Rust for a much faster user experience. There is no noticeable delay when importing new entries.
* Embedded SQLite 3.17.
* Simplified the history output parser: it now only handles Unix timestamps. This avoids converting between timestamps multiple times (in `history` output and `duiker import`).
* Renamed `stats` to `top` and removed database statistics.

0.1.0
~~~~~

Initial release.
