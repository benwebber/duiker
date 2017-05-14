import pathlib
import sqlite3
from typing import (
    Any,
    Callable,
    Tuple,
    Union,
)


Database = Union[sqlite3.Connection, pathlib.Path, str]
RowFactory = Callable[[sqlite3.Cursor, Tuple], Any]
