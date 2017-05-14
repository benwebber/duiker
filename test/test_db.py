import sqlite3

import pytest

from duiker import db


@pytest.mark.parametrize('database', [':memory:', ':tempfile:'], indirect=True)
@pytest.mark.parametrize('row_factory', [None, sqlite3.Row])
def test_query(database, row_factory):
    with database:
        database.row_factory = row_factory
        points = list(database.execute('SELECT * FROM points'))

    def callback(rows, *args, **kwargs):
        assert list(rows) == points

    path = pytest.helpers.get_database_path(database) or database

    db.query(path, 'SELECT * FROM points', row_factory=row_factory)(callback)()


def test_query_invalid_database():
    with pytest.raises(TypeError):
        db.query(None, 'SELECT * FROM points', row_factory=None)(None)()
