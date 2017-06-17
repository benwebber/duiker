duiker
======

|travis|

Automatically index your shell history in a full-text search database. Magic!

Features
--------

-  Uses SQLite3's excellent `FTS4 <https://sqlite.org/fts3.html>`__
   extension to provide full-text search.
-  Respects ``HISTTIMEFORMAT`` if set.

Requirements
------------

-  Bash

Install
-------

Download the `latest release <https://github.com/benwebber/duiker/releases>__` and extract it somewhere on your ``$PATH``.

Alternatively, install Duiker from source. To build the package you will need:

-  `jq <https://stedolan.github.io/jq/>__`
-  Rust 1.17+ (`install with rustup <https://www.rust-lang.org/en-US/install.html>`__)

Simply run:

::

    make install

Setup
-----

Import your existing shell history:

::

    HISTTIMEFORMAT='%s ' history | duiker import -

Configuration
-------------

If you want to automatically import your shell history on-the-fly, you
can add ``duiker import`` to your ``PROMPT_COMMAND`` [#]_.

Run ``duiker magic`` to print a shell snippet that automatically imports
your last command into Duiker:

::

    duiker magic

Configure this shell snippet as part of your ``PROMPT_COMMAND``. Run
``duiker magic --help`` for an example.

Searching
---------

Duiker indexes your shell history in an SQLite3 full-text search table.

You can use any ``MATCH`` [#]_ expression to search the database:

::

    $ duiker search git
    2017-04-13 15:50:02 	git staged
    2017-04-13 15:50:14 	git commit -a
    2017-04-13 15:55:07 	git diff

::

    $ duiker search '(git OR fossil) diff'
    2017-04-27 15:15:01 	git diff
    2017-04-27 15:15:49 	git diff
    2017-04-28 14:49:19 	fossil diff
    2017-04-28 14:53:09 	fossil diff src/main.rs

::

    $ duiker search 'sqlite*'
    2017-03-04 19:00:42 	sqlite3 db.sqlite
    2017-03-04 19:13:11 	rm db.sqlite

Limitations
-----------

Duiker only supports Bash at present. Pull requests for other shells
welcome.

License
-------

MIT

.. [#] `<https://www.gnu.org/software/bash/manual/html_node/Controlling-the-Prompt.html#Controlling-the-Prompt>`_
.. [#] `<https://sqlite.org/fts3.html#full_text_index_queries>`_

.. |travis| image:: https://travis-ci.org/benwebber/curlrc.svg?branch=master
    :target: https://travis-ci.org/benwebber/duiker
