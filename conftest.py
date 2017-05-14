import random
import sqlite3

import pytest

pytest_plugins = ['helpers_namespace']


@pytest.helpers.register
def get_database_path(connection, database='main'):
    """
    Queries SQLite connection for the path to a specific database.

    Returns None if the database is in-memory.
    """
    with connection:
        for row in connection.execute('PRAGMA database_list'):
            _, name, addr = row
            if name == database:
                return addr if addr else None


@pytest.fixture
def database(request, tmpdir):
    """
    Populate a test database.

    If request.param is ':memory:' or None, create an in-memory database.

    If request.param is ':tempfile:', create a temporary database on disk.
    """
    path = getattr(request, 'param', ':memory:')
    if path not in {':memory:', ':tempfile:'}:
        raise ValueError('invalid fixture parameter: {}'.format(request.param))
    path = str(tmpdir.join('test.db')) if path == ':tempfile:' else path
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE points (x FLOAT, y FLOAT)')
    points = [(random.random(), random.random()) for i in range(0, 10)]
    with db:
        for point in points:
            db.execute('INSERT INTO points VALUES (?, ?)', point)
    return db
