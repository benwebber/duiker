from collections import namedtuple
import datetime as dt
import os
import time
from typing import Tuple


class ParseError(Exception):
    pass


class Command(namedtuple('Command', ('id', 'timestamp', 'command'))):
    @classmethod
    def from_row(cls, cursor, row):
        return Command(*row)

    def __format__(self, fmt):
        if fmt == 'tsv':
            timestamp = render_timestamp(self.timestamp)
            return '{timestamp}\t{self.command}'.format(timestamp=timestamp, self=self)
        return repr(self)


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


def render_timestamp(timestamp):
    fmt = os.environ.get('HISTTIMEFORMAT')
    return dt.datetime.fromtimestamp(timestamp).strftime(fmt) if fmt else timestamp


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
