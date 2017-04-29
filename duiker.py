#!/usr/bin/env python3

"""
Automatically index your shell history in a full-text search database. Magic!
"""

import argparse
from collections import namedtuple
from datetime import datetime as dt
import logging
import io
import os
import pathlib
import re
import sqlite3
import sys
import textwrap
import time

__version__ = '0.1.0'

XDG_DATA_HOME = os.environ.get('XDG_DATA_HOME', '~/.local/share')
DUIKER_HOME = os.environ.get('DUIKER_HOME', pathlib.Path(XDG_DATA_HOME, 'duiker'))
DUIKER_DB = DUIKER_HOME / 'duiker.db'
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

stdout = logging.StreamHandler(sys.stdout)

logger.addHandler(stdout)


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

    HISTLINE_EXPR = re.compile(r'^\s*\d+\s+(?P<remainder>.*)', flags=re.M)

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS history (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL,
        command   TEXT NOT NULL,
                  UNIQUE (timestamp, command) ON CONFLICT REPLACE
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS fts_history USING fts4(history_id, command);

    CREATE VIRTUAL TABLE IF NOT EXISTS fts_history_terms USING fts4aux(fts_history);
    """
    SCHEMA_VERSION = 1

    def __init__(self, db, create=True):
        self.db = db

        # We want to split each history line into two components: timestamp and
        # command.
        #
        # Unfortunately, Bash doesn't use special characters to delimit these
        # fields. Furthermore, if HISTTIMEFORMAT contains spaces, we can't use
        # str.split().
        #
        # Instead, calculate the string length of the timestamp by rendering a
        # sample date with the same format. Use this as an offset to split the
        # fields.
        self.hist_time_format = os.environ.get('HISTTIMEFORMAT')
        if self.hist_time_format:
            prefix = dt.fromtimestamp(0).strftime(self.hist_time_format)
            self._hist_offset = len(prefix)
        else:
            self._hist_offset = 0

        if create:
            DUIKER_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
            with sqlite3.connect(self.db) as db:
                db.executescript(self.SCHEMA)
                db.execute('PRAGMA user_version = {}'.format(self.SCHEMA_VERSION))

    def import_file(self, histfile):
        with sqlite3.connect(self.db) as db:
            for line in histfile:
                try:
                    command = self._parse_line(line)
                except AttributeError:
                    # Record did not match regex (possibly invalid).
                    continue
                db.execute('INSERT INTO history VALUES (?, ?, ?)', command)
                db.execute('INSERT INTO fts_history SELECT id, command FROM history WHERE rowid = last_insert_rowid()')
                logger.info('Imported `%s` issued %s', command.command, render_timestamp(command.timestamp))

    def _parse_line(self, line):
        # Strip history file line ID.
        match = self.HISTLINE_EXPR.match(line)
        remainder = match.group('remainder')
        if self.hist_time_format:
            timestamp = dt.strptime(remainder[:self._hist_offset], self.hist_time_format)
            command = remainder[self._hist_offset:]
        else:
            timestamp = time.mktime(dt.now().timetuple())
            command = remainder
        return Command(None, time.mktime(timestamp.timetuple()), command)

    def _execute(self, query, params=None):
        params = params if params else ()
        with sqlite3.connect(self.db) as db:
            db.row_factory = Command.from_row
            yield from db.execute(query, params)

    def log(self):
        query = 'SELECT * FROM history ORDER BY timestamp ASC'
        return self._execute(query)

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

    def search(self, expr):
        fts = '''SELECT history.*
                   FROM fts_history
                   JOIN history
                     ON fts_history.history_id = history.id
                  WHERE fts_history MATCH ?;'''
        return self._execute(fts, (expr,))

    def head(self, num):
        query = '''SELECT * FROM history ORDER BY timestamp ASC LIMIT ?'''
        return self._execute(query, (num,))

    def tail(self, num):
        query = '''SELECT * FROM history ORDER BY timestamp DESC LIMIT ?'''
        return self._execute(query, (num,))

    def shell(self, *args):
        os.execvp('sqlite3', ['sqlite3'] + list(args) + [self.db])


def sizeof_human(size, binary=True):
    """
    Render human-readable file sizes.

    Adapted from: <http://stackoverflow.com/a/1094933>.
    """
    mod = 1024 if binary else 1000
    prefixes = [prefix + 'i' if (prefix and binary) else prefix
                for prefix in ('', 'k', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')]
    for prefix in prefixes[:-1]:
        if abs(size) < mod:
            return '{size:.1f} {prefix}B'.format(size=size, prefix=prefix)
        size /= mod
    return '{size:.1f} {prefix}B'.format(size=size, prefix=prefixes[-1])


def render_timestamp(timestamp):
    fmt = os.environ.get('HISTTIMEFORMAT')
    return dt.fromtimestamp(timestamp).strftime(fmt) if fmt else timestamp


def handle_import(args):
    duiker = Duiker(DUIKER_DB.as_posix())
    duiker.import_file(args.histfile)


def handle_search(args):
    duiker = Duiker(DUIKER_DB.as_posix())
    for command in duiker.search(args.expression):
        logger.info('{:tsv}'.format(command))


def handle_log(args):
    duiker = Duiker(DUIKER_DB.as_posix())
    for command in duiker.log():
        logger.info('{:tsv}'.format(command))


def handle_head(args):
    duiker = Duiker(DUIKER_DB.as_posix())
    for command in duiker.head(args.entries):
        logger.info('{:tsv}'.format(command))


def handle_tail(args):
    duiker = Duiker(DUIKER_DB.as_posix())
    for command in duiker.tail(args.entries):
        logger.info('{:tsv}'.format(command))


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
    search.set_defaults(func=handle_search)

    log = subparsers.add_parser('log', description='Show commands from all time.')
    log.set_defaults(func=handle_log)

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
    head.set_defaults(func=handle_head)

    tail = subparsers.add_parser('tail', description='Show last N commands.')
    tail.add_argument('-n', '--entries', help='recall last N commands [%(default)s]', default=10)
    tail.set_defaults(func=handle_tail)

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

    if args.command == 'import':
        if args.quiet:
            logger.setLevel(logging.CRITICAL)
        if args.histfile is sys.stdin:
            # Python opens stdin in strict mode by default.
            args.histfile = io.TextIOWrapper(sys.stdin.buffer, errors='replace')

    if HISTTIMEFORMAT:
        try:
            timestamp = dt.now().strftime(HISTTIMEFORMAT)
            dt.strptime(timestamp, HISTTIMEFORMAT)
        except ValueError:
            error('Cannot parse HISTTIMEFORMAT ({}).'.format(HISTTIMEFORMAT))
            hint('Use only standard format codes: <https://docs.python.org/3/library/datetime.html#strftime-and-strptime-behavior>.')
            sys.exit(1)

    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit()


if __name__ == '__main__':
    main()
