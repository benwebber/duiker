#!/usr/bin/env python3

"""
Automatically index your shell history in a full-text search database. Magic!
"""

import argparse
from collections import namedtuple
import datetime as dt
from functools import wraps
import logging
import io
import os
import pathlib
import sqlite3
import sys
import textwrap
import time
from typing import (
    Any,
    Callable,
    Optional,
    Tuple,
    Union,
)

from . import db

__version__ = '0.1.0'


Database = Union[sqlite3.Connection, pathlib.Path, str]
RowFactory = Callable[[sqlite3.Cursor, Tuple], Any]


def xdg_data_home(name: Optional[str] = None) -> pathlib.Path:
    """
    Return the XDG Base Directory Specification data directory for a specific
    application, or the base directory itself.
    """
    home = pathlib.Path(os.path.expanduser(os.environ.get('XDG_DATA_HOME') or '~/.local/share'))
    return home / name if name else home


DUIKER_HOME = xdg_data_home('duiker')
DUIKER_DB = DUIKER_HOME.expanduser() / 'duiker.db'
HISTTIMEFORMAT = os.environ.get('HISTTIMEFORMAT')

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


class ParseError(Exception):
    pass


class PrefixWrapper(textwrap.TextWrapper):
    def __init__(self, prefix, *args, **kwargs):
        super().__init__(*args, initial_indent=prefix, subsequent_indent=prefix,
                         break_long_words=False, break_on_hyphens=False,
                         **kwargs)


class Command(namedtuple('Command', ('id', 'timestamp', 'command'))):
    @classmethod
    def from_row(cls, cursor, row):
        return Command(*row)

    def __format__(self, fmt):
        if fmt == 'tsv':
            timestamp = render_timestamp(self.timestamp)
            return '{timestamp}\t{self.command}'.format(timestamp=timestamp, self=self)
        return repr(self)


class Duiker:

    def __init__(self, db, create=True):
        self.db = db

        if create:
            DUIKER_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)

    def import_file(self, histfile):
        histtimeformat = os.environ.get('HISTTIMEFORMAT')
        with sqlite3.connect(self.db) as db:
            for line in histfile:
                try:
                    command = parse_history_line(line, histtimeformat)
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


def _execute(conn: sqlite3.Connection, callback: Callable, query: str, values: Optional[Tuple] = (), row_factory: Optional[RowFactory] = None, **kwargs) -> Callable:
    if row_factory:
        conn.row_factory = row_factory
    cursor = conn.execute(query, values)
    return callback(cursor, *values, **kwargs)


def query(db: Database, query: str, *defaults: Optional[Tuple], row_factory: RowFactory = Command.from_row) -> Callable[..., Any]:
    """
    Executes the given query and passes the cursor to the wrapped function.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            values = args if args else defaults
            if isinstance(db, sqlite3.Connection):
                return _execute(db, func, query, values, row_factory=row_factory)
            elif isinstance(db, (pathlib.Path, str)):
                addr = str(db)
                with sqlite3.connect(addr) as conn:
                    return _execute(conn, func, query, values, row_factory=row_factory)
            else:
                raise TypeError("'db' must be {}".format(str(Database)))
        return wrapper
    return decorator


def parse_history_line(line, histtimeformat=None):
    """
    Extract the timestamp and command from a line of `history` output.
    """
    # Split line ID and timestamp/command (remainder).
    _, remainder = line.split(None, 1)
    remainder = remainder.rstrip()
    if histtimeformat:
        timestamp, command = strptime_prefix(remainder, histtimeformat)
        command = command.strip()
        timestamp = time.mktime(timestamp.timetuple())
    else:
        command = remainder
        timestamp = None
    return Command(None, timestamp, command)


def strptime_prefix(text: str, fmt: str) -> Tuple[dt.datetime, str]:
    """
    Partially parse a string beginning with a datetime representation.

    Returns the datetime and the rest of the string ("unconverted data").

    >>> strptime_prefix('1970-01-01 hello world', '%Y-%m-%d')
    (datetime.datetime(1970, 1, 1, 0, 0), ' hello world')

    >>> strptime_prefix('hello world', '%Y-%m-%d')
    Traceback (most recent call last):
    ...
    ValueError: time data 'hello world' does not match format '%Y-%m-%d'

    >>> strptime_prefix('hello world 1970-01-01', '%Y-%m-%d')
    Traceback (most recent call last):
    ...
    ValueError: time data 'hello world 1970-01-01' does not match format '%Y-%m-%d'
    """
    # datetime.strptime() raises ValueError if the string does not exactly
    # match the format string.
    try:
        # Dummy test: we need to inspect the ValueError.
        dt.datetime.strptime(text, fmt)
    except ValueError as exc:
        # Extract the command from the ValueError error message and re-parse
        # the timestamp. This feels quite fragile, but this error message
        # hasn't changed since 2.3:
        #
        # <https://github.com/python/cpython/blame/v3.6.1/Lib/_strptime.py#L363-L365>
        message = exc.args[0]
        if 'unconverted data remains: ' in message:
            remainder = exc.args[0].replace('unconverted data remains: ', '')
            timestamp = text.replace(remainder, '')
            return dt.datetime.strptime(timestamp, fmt), remainder
        else:
            # Raised another sort of ValueError.
            raise


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


def render_timestamp(timestamp):
    fmt = os.environ.get('HISTTIMEFORMAT')
    return dt.datetime.fromtimestamp(timestamp).strftime(fmt) if fmt else timestamp


def handle_import(args):
    duiker = Duiker(DUIKER_DB.as_posix())
    try:
        duiker.import_file(args.histfile)
    except ParseError as exc:
        error(str(exc))


@query(DUIKER_DB, '''SELECT history.*
                       FROM fts_history
                       JOIN history
                         ON fts_history.history_id = history.id
                      WHERE fts_history MATCH ?''')
def handle_search(commands, *params):
    for command in commands:
        print('{:tsv}'.format(command))


@query(DUIKER_DB, 'SELECT * FROM history ORDER BY timestamp ASC')
def handle_log(commands, *params):
    for command in commands:
        print('{:tsv}'.format(command))


@query(DUIKER_DB, 'SELECT * FROM history ORDER BY timestamp ASC LIMIT ?')
def handle_head(commands, *params):
    for command in commands:
        print('{:tsv}'.format(command))


@query(DUIKER_DB, 'SELECT * FROM history ORDER BY timestamp DESC LIMIT ?')
def handle_tail(commands, *params):
    for command in commands:
        print('{:tsv}'.format(command))


def handle_shell(args):
    duiker = Duiker(DUIKER_DB.as_posix())
    duiker.shell(*args.sqlite3_options)


def handle_magic(args):
    print(MAGIC.strip())


def handle_version(args):
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
    subparsers = parser.add_subparsers(dest='command')
    # Python 3.3 introduced a regression that makes subparsers optional:
    # <http://bugs.python.org/issue9253>
    subparsers.required = True

    import_ = subparsers.add_parser(
        'import',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='''
Import Bash history file into Duiker.

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
        description='''
Search for a command. Use any SQLite full-text search (FTS) query:

    <https://sqlite.org/fts3.html#full_text_index_queries>
'''.strip()
    )
    search.add_argument('expression')

    log = subparsers.add_parser('log', description='Show commands from all time.')

    magic = subparsers.add_parser(
        'magic',
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        description='Print stats for the history database.',
    )
    stats.set_defaults(func=handle_stats)

    version = subparsers.add_parser('version', description='Show version and exit.')
    version.set_defaults(func=handle_version)

    head = subparsers.add_parser('head', description='Show first N commands.')
    head.add_argument('-n', '--entries', help='recall first N commands [%(default)s]', default=10)

    tail = subparsers.add_parser('tail', description='Show last N commands.')
    tail.add_argument('-n', '--entries', help='recall last N commands [%(default)s]', default=10)

    shell = subparsers.add_parser(
        'sqlite3',
        aliases=['sql', 'shell'],
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
