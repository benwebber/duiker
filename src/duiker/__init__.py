#!/usr/bin/env python3

"""
Automatically index your shell history in a full-text search database. Magic!
"""

import argparse
import datetime as dt
import logging
import io
import os
import pathlib
import sqlite3
import sys
import textwrap
import time
from typing import Optional

from . import db
from .config import *
from .parser import (
    Command,
    ParseError,
    parse_history_line,
    render_timestamp,
    strptime_prefix,
)

__version__ = '0.1.0'


MAGIC = '''
__duiker_import() {
    local old_histignore=$HISTIGNORE
    HISTIGNORE='history*'
    history 1 | duiker import --quiet -
    HISTIGNORE=$old_histignore
}'''

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

stderr = logging.StreamHandler(sys.stderr)

logger.addHandler(stderr)


class PrefixWrapper(textwrap.TextWrapper):
    def __init__(self, prefix, *args, **kwargs):
        super().__init__(*args, initial_indent=prefix, subsequent_indent=prefix,
                         break_long_words=False, break_on_hyphens=False,
                         **kwargs)


class Duiker:

    def __init__(self, db, create=True):
        self.db = db

        if create:
            DUIKER_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)

    def import_file(self, histfile):
        with sqlite3.connect(self.db) as db:
            for line in histfile:
                try:
                    command = parse_history_line(line, HISTTIMEFORMAT)
                except Exception as exc:
                    raise ParseError(exc)
                if command.timestamp is None:
                    command = command._replace(timestamp=time.mktime(dt.datetime.now().timetuple()))
                db.execute('INSERT INTO history VALUES (?, ?, ?)', command)
                db.execute('INSERT INTO fts_history SELECT id, command FROM history WHERE rowid = last_insert_rowid()')
                logger.info('Imported `%s` issued %s', command.command, render_timestamp(command.timestamp))

    def stats(self):
        stats = {
            'Database': sizeof_human(pathlib.Path(self.db).stat().st_size),
        }
        queries = {
            'Indexed Terms': 'SELECT COUNT(term) FROM fts_history_terms',
            'Unique Indexed Terms': 'SELECT COUNT(DISTINCT term) FROM fts_history_terms',
            'Commands': 'SELECT COUNT(command) FROM history',
            'Unique Commands': 'SELECT COUNT(DISTINCT command) from history',
        }
        with sqlite3.connect(self.db) as db:
            for stat, query in queries.items():
                stats[stat] = db.execute(query).fetchone()[0]
        query = 'SELECT COUNT(*) AS frequency, command FROM history GROUP BY command ORDER BY frequency DESC LIMIT 100;'
        stats['Frequent Commands'] = []
        with sqlite3.connect(self.db) as db:
            for row in db.execute(query):
                stats['Frequent Commands'].append(row)
        return stats

    def shell(self, *args):
        os.execvp('sqlite3', ['sqlite3'] + list(args) + [self.db])


def sizeof_human(size, binary=True):
    """
    Render human-readable file sizes.

    Adapted from: <http://stackoverflow.com/a/1094933>.
    """
    if binary:
        mod = 1024
        prefixes = ('', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi', 'Yi')
    else:
        mod = 1000
        prefixes = ('', 'k', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')
    for prefix in prefixes[:-1]:
        if abs(size) < mod:
            return '{size:.1f} {prefix}B'.format(size=size, prefix=prefix)
        size /= mod
    return '{size:.1f} {prefix}B'.format(size=size, prefix=prefixes[-1])


def handle_import(args):
    duiker = Duiker(DUIKER_DB.as_posix())
    try:
        duiker.import_file(args.histfile)
    except ParseError as exc:
        error(str(exc))


@db.query(DUIKER_DB, '''SELECT history.*
                          FROM fts_history
                          JOIN history
                            ON fts_history.history_id = history.id
                         WHERE fts_history MATCH ?''')
def handle_search(commands, *params):
    for command in commands:
        print('{:tsv}'.format(command))


@db.query(DUIKER_DB, 'SELECT * FROM history ORDER BY timestamp ASC')
def handle_log(commands, *params):
    for command in commands:
        print('{:tsv}'.format(command))


@db.query(DUIKER_DB, 'SELECT * FROM history ORDER BY timestamp ASC LIMIT ?')
def handle_head(commands, *params):
    for command in commands:
        print('{:tsv}'.format(command))


@db.query(DUIKER_DB, 'SELECT * FROM history ORDER BY timestamp DESC LIMIT ?')
def handle_tail(commands, *params):
    for command in commands:
        print('{:tsv}'.format(command))


def handle_shell(args):
    duiker = Duiker(DUIKER_DB.as_posix())
    duiker.shell(*args.sqlite3_options)


def handle_magic(args):
    print(MAGIC.strip())


def handle_version(args):
    if args.verbose:
        migrator = db.Migrator(str(DUIKER_DB))
        print('duiker {} (schema version {})'.format(__version__, migrator.user_version))
        print('SQLite3 {}'.format(sqlite3.sqlite_version))
        print('pysqlite {}'.format(sqlite3.version))
    else:
        print('duiker {}'.format(__version__))


def handle_stats(args):
    duiker = Duiker(DUIKER_DB.as_posix())
    for stat, value in duiker.stats().items():
        if isinstance(value, list):
            max_freq = max(item[0] for item in value)
            padding = len(str(max_freq))
            print('{stat}:'.format(stat=stat))
            for item in value:
                frequency, command = item
                print('\t{frequency:{padding}}\t{command}'.format(frequency=frequency, padding=padding, command=command))
        else:
            print('{stat}: {value}'.format(stat=stat, value=value))


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(title='commands', dest='command', metavar='')
    # Python 3.3 introduced a regression that makes subparsers optional:
    # <http://bugs.python.org/issue9253>
    subparsers.required = True

    import_ = subparsers.add_parser(
        'import',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help='Import Bash history output into database.',
        description='''
Import Bash history output into Duiker.

Import from standard input:

    history | duiker import -

Import from history output:

    history > history_file
    duiker import history_file
'''.strip())
    import_.add_argument(
        'histfile',
        type=argparse.FileType('r', errors='replace'),
        help='history file to import [standard input]',
    )
    import_.add_argument(
        '-q', '--quiet',
        action='store_true', default=False,
        help='do not print imported commands',
    )
    import_.set_defaults(func=handle_import)

    search = subparsers.add_parser(
        'search',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help='Search for a command in the history database.',
        description='''
Search for a command. Use any SQLite full-text search (FTS) query:

    <https://sqlite.org/fts3.html#full_text_index_queries>
'''.strip()
    )
    search.add_argument('expression')

    log = subparsers.add_parser('log', help='Show commands from all time.', description='Show commands from all time.')

    magic = subparsers.add_parser(
        'magic',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help='Print shell snippet that imports last command.',
        description='''
Print shell function that imports last command into Duiker.

Add this function to your $PROMPT_COMMAND:

    {magic}

    __prompt() {{
        history -a
        __duiker_import
        PS1="\\u@\\h:\\w$ "
    }}

    PROMPT_COMMAND=__prompt
'''.format(magic=textwrap.indent(MAGIC, '    ').strip()).strip())
    magic.set_defaults(func=handle_magic)

    stats = subparsers.add_parser(
        'stats',
        help='Print stats for the history database.',
        description='Print stats for the history database.',
    )
    stats.set_defaults(func=handle_stats)

    version = subparsers.add_parser('version', help='Show version and exit.', description='Show version and exit.')
    version.add_argument('-v', '--verbose', action='store_true', help='Print extra version information.')
    version.set_defaults(func=handle_version)

    head = subparsers.add_parser('head', help='Show first N commands.', description='Show first N commands.')
    head.add_argument('-n', '--entries', help='recall first N commands [%(default)s]', default=10)

    tail = subparsers.add_parser('tail', help='Show last N commands.', description='Show last N commands.')
    tail.add_argument('-n', '--entries', help='recall last N commands [%(default)s]', default=10)

    shell = subparsers.add_parser(
        'sqlite3',
        aliases=['sql', 'shell'],
        help='Open the database in the SQLite3 shell.',
        description='Open the database in the SQLite3 shell.',
    )
    shell.add_argument(
        'sqlite3_options',
        metavar='OPTIONS', nargs=argparse.REMAINDER,
        help='Pass all options after `--` to SQLite3 shell.',
    )
    shell.set_defaults(func=handle_shell)

    return parser.parse_args(argv)


def error(message):
    print('\n'.join(PrefixWrapper('error: ').wrap(message)), file=sys.stderr)


def hint(message):
    print('\n'.join(PrefixWrapper('hint: ').wrap(message)), file=sys.stderr)


def main():
    args = parse_args(sys.argv[1:])

    migrator = db.Migrator(str(DUIKER_DB))
    applied_migrations = set(migrator.applied_migrations)
    if not applied_migrations:
        migrator.user_version = 0
    migrations = db.sort_migrations()
    for migration in migrations:
        if migration not in applied_migrations:
            migration_module = db.get_migration(migration)
            logger.info('Applying migration: {}'.format(migration_module.__doc__.strip()))
            migrator.apply(migration_module)

    if args.command == 'import':
        if args.quiet:
            logger.setLevel(logging.CRITICAL)
        if args.histfile is sys.stdin:
            # Python opens stdin in strict mode by default.
            args.histfile = io.TextIOWrapper(sys.stdin.buffer, errors='replace')

    if HISTTIMEFORMAT:
        try:
            timestamp = dt.datetime.now().strftime(HISTTIMEFORMAT)
            dt.datetime.strptime(timestamp, HISTTIMEFORMAT)
        except ValueError:
            error('Cannot parse HISTTIMEFORMAT ({}).'.format(HISTTIMEFORMAT))
            hint('Use only standard format codes: <https://docs.python.org/3/library/datetime.html#strftime-and-strptime-behavior>.')
            sys.exit(1)

    try:
        args.func(args)
    except AttributeError:
        if args.command == 'search':
            handle_search(args.expression)
        elif args.command == 'log':
            handle_log()
        elif args.command == 'head':
            handle_head(args.entries)
        elif args.command == 'tail':
            handle_tail(args.entries)
    except KeyboardInterrupt:
        sys.exit()


if __name__ == '__main__':
    main()
