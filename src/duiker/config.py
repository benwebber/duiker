import os
import pathlib
from typing import Optional


__all__ = ['DUIKER_HOME', 'DUIKER_DB', 'HISTTIMEFORMAT']


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
