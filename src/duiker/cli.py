import datetime as dt
import logging
import sqlite3
import textwrap
import time
import sys

import click

from . import db
from .config import *
from .parser import (
    Command,
    parse_history_line,
    render_timestamp,
)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

stderr = logging.StreamHandler(sys.stderr)

logger.addHandler(stderr)


class PrefixWrapper(textwrap.TextWrapper):
    def __init__(self, prefix, *args, **kwargs):
        super().__init__(*args, initial_indent=prefix, subsequent_indent=prefix,
                         break_long_words=False, break_on_hyphens=False,
                         **kwargs)


def error(message):
    print('\n'.join(PrefixWrapper('error: ').wrap(message)), file=sys.stderr)


def hint(message):
    print('\n'.join(PrefixWrapper('hint: ').wrap(message)), file=sys.stderr)


class AliasedGroup(click.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aliases = {}

    def command(self, *args, **kwargs):
        aliases = kwargs.pop('aliases', [])
        def decorator(func):
            cmd = click.decorators.command(*args, **kwargs)(func)
            self.add_command(cmd, aliases=aliases)
            return cmd
        return decorator

    def add_command(self, cmd, name=None, aliases=None):
        super().add_command(cmd, name)
        if aliases:
            for alias in aliases:
                self._aliases[alias] = name or cmd.name

    def get_command(self, ctx, cmd_name):
        command = super().get_command(ctx, cmd_name)
        if command is None:
            command = super().get_command(ctx, self._aliases.get(cmd_name))
        return command


@click.group('duiker', cls=AliasedGroup)
@click.pass_context
def cli(ctx):
    DUIKER_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    ctx.obj = {'DB': str(DUIKER_DB)}

    migrator = db.Migrator(DUIKER_DB)
    applied_migrations = set(migrator.applied_migrations)
    if not applied_migrations:
        migrator.database.user_version = 0
    migrations = db.sort_migrations()
    for migration in migrations:
        if migration not in applied_migrations:
            migration_module = db.get_migration(migration)
            logger.info('Applying migration: {}'.format(migration_module.__doc__.strip()))
            migrator.apply(migration_module)

    if HISTTIMEFORMAT:
        try:
            timestamp = dt.datetime.now().strftime(HISTTIMEFORMAT)
            dt.datetime.strptime(timestamp, HISTTIMEFORMAT)
        except ValueError:
            error('Cannot parse HISTTIMEFORMAT ({}).'.format(HISTTIMEFORMAT))
            hint('Use only standard format codes: <https://docs.python.org/3/library/datetime.html#strftime-and-strptime-behavior>.')
            sys.exit(1)



@cli.command()
@click.option('-n', '--entries', type=click.INT, default=20, show_default=True, help='recall last N commands')
@click.pass_context
def head(ctx, entries):
    """
    Show first N commands.
    """
    query = 'SELECT * FROM history ORDER BY timestamp ASC LIMIT ?'
    with sqlite3.connect(ctx.obj['DB']) as connection:
        connection.row_factory = Command.from_row
        for command in connection.execute(query, (entries,)):
            print('{:tsv}'.format(command))


@cli.command('import')
@click.argument('histfile', type=click.File(errors='replace'))
@click.option('-q', '--quiet', is_flag=True, help='do not print imported commands')
@click.pass_context
def _import(ctx, histfile, quiet):
    """
    Import Bash history output into database.

    Import from standard input:

        \bhistory | duiker import -

    Import from history output:

        \bhistory > history_file
        \bduiker import history_file
    """
    if quiet:
        logger.setLevel(logging.CRITICAL)

    with sqlite3.connect(ctx.obj['DB']) as db:
        for line in histfile:
            try:
                command = parse_history_line(line, HISTTIMEFORMAT)
            except Exception as exc:
                raise click.ClickException(exc)
            if command.timestamp is None:
                command = command._replace(timestamp=time.mktime(dt.datetime.now().timetuple()))
            db.execute('INSERT INTO history VALUES (?, ?, ?)', command)
            db.execute('INSERT INTO fts_history SELECT id, command FROM history WHERE rowid = last_insert_rowid()')
            logger.info('Imported `%s` issued %s', command.command, render_timestamp(command.timestamp))


@cli.command()
@click.pass_context
def log(ctx):
    """
    Show commands from all time.
    """
    query = 'SELECT * FROM history ORDER BY timestamp'
    with sqlite3.connect(ctx.obj['DB']) as connection:
        connection.row_factory = Command.from_row
        for command in connection.execute(query):
            print('{:tsv}'.format(command))


@cli.command(epilog="""Example:

    \b
{}

    \b
__prompt() {{
  history -a
  __duiker_import
  PS1="\\u@\\h:\\w$ "
}}

    \b
PROMPT_COMMAND=__prompt
    \b
""".format(MAGIC))
@click.pass_context
def magic(ctx):
    """
    Print shell function that imports last command into Duiker.
    """
    print(MAGIC)


@cli.command()
@click.argument('expression')
@click.pass_context
def search(ctx, expression):
    """
    Search for a command in the history database.

    Use any SQLite full-text search (FTS) query:

        \bhttps://sqlite.org/fts3.html#full_text_index_queries
    """
    query = '''SELECT history.*
                 FROM fts_history
                 JOIN history
                   ON fts_history.history_id = history.id
                WHERE fts_history MATCH ?'''
    with sqlite3.connect(ctx.obj['DB']) as connection:
        connection.row_factory = Command.from_row
        for command in connection.execute(query, (expression,)):
            print('{:tsv}'.format(command))


@cli.command('sqlite3', aliases=['sql', 'shell'])
@click.argument('sqlite3_options', nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def shell(ctx, sqlite3_options):
    """
    Open the database in an SQLite3 shell.
    """
    import os
    os.execvp('sqlite3', ['sqlite3'] + list(sqlite3_options) + [ctx.obj['DB']])


@cli.command()
@click.pass_context
def stats(ctx):
    """
    Print stats for the history database.
    """
    import pathlib
    stats = {
        'Database': sizeof_human(pathlib.Path(ctx.obj['DB']).stat().st_size),
    }
    queries = {
        'Indexed Terms': 'SELECT COUNT(term) FROM fts_history_terms',
        'Unique Indexed Terms': 'SELECT COUNT(DISTINCT term) FROM fts_history_terms',
        'Commands': 'SELECT COUNT(command) FROM history',
        'Unique Commands': 'SELECT COUNT(DISTINCT command) from history',
    }
    with sqlite3.connect(ctx.obj['DB']) as db:
        for stat, query in queries.items():
            stats[stat] = db.execute(query).fetchone()[0]
    query = 'SELECT COUNT(*) AS frequency, command FROM history GROUP BY command ORDER BY frequency DESC LIMIT 100;'
    stats['Frequent Commands'] = []
    with sqlite3.connect(ctx.obj['DB']) as db:
        for row in db.execute(query):
            stats['Frequent Commands'].append(row)

    for stat, value in stats.items():
        if isinstance(value, list):
            max_freq = max(item[0] for item in value)
            padding = len(str(max_freq))
            print('{stat}:'.format(stat=stat))
            for item in value:
                frequency, command = item
                print('\t{frequency:{padding}}\t{command}'.format(frequency=frequency, padding=padding, command=command))
        else:
            print('{stat}: {value}'.format(stat=stat, value=value))


@cli.command()
@click.option('-n', '--entries', type=click.INT, default=20, show_default=True, help='recall last N commands')
@click.pass_context
def tail(ctx, entries):
    """
    Show last N commands.
    """
    query = 'SELECT * FROM (SELECT * FROM history ORDER BY timestamp DESC LIMIT ?) ORDER BY timestamp ASC;'
    with sqlite3.connect(ctx.obj['DB']) as connection:
        connection.row_factory = Command.from_row
        for command in connection.execute(query, (entries,)):
            print('{:tsv}'.format(command))


@cli.command()
@click.option('-v', '--verbose', is_flag=True, help='print extra version information')
@click.pass_context
def version(ctx, verbose):
    """
    Show version and exit.
    """
    from . import __version__
    if verbose:
        database = db.DAO(DUIKER_DB)
        print('duiker {} (schema version {})'.format(__version__, database.user_version))
        print('SQLite3 {}'.format(sqlite3.sqlite_version))
        print('pysqlite {}'.format(sqlite3.version))
    else:
        print('duiker {}'.format(__version__))


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
