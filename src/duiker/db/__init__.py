import importlib
import pkgutil
import sqlite3

from .. import dag


class MigrationError(Exception):
    pass


class MigrationGraph:
    def __init__(self, migrations):
        self.graph = dag.DAG()
        for module in migrations:
            name = get_migration_name(module)
            if hasattr(module, '__depends__'):
                for dependency in module.__depends__:
                    self.graph.add(dependency, name)
            else:
                self.graph[name]

    def sort(self):
        return dag.tsort(self.graph)


class Migrator:
    def __init__(self, database, create_migrations_table=True):
        self.database = database

        if create_migrations_table:
            with self.connection as connection:
                connection.execute('CREATE TABLE IF NOT EXISTS migrations (name TEXT NOT NULL UNIQUE)')

    @property
    def applied_migrations(self):
        return list(self.iter_applied_migrations())

    @property
    def connection(self):
        return sqlite3.connect(self.database)

    @property
    def user_version(self):
        with self.connection as connection:
            return connection.execute('PRAGMA user_version').fetchone()[0]

    @user_version.setter
    def user_version(self, version):
        with self.connection as connection:
            connection.execute('PRAGMA user_version = {}'.format(version))

    def _delete(self, migration):
        name = get_migration_name(migration)
        with self.connection as connection:
            connection.execute('DELETE FROM migrations WHERE name = ?', (name,))

    def _insert(self, migration):
        name = get_migration_name(migration)
        with self.connection as connection:
            connection.execute('INSERT INTO migrations VALUES (?)', (name,))

    def apply(self, migration):
        with self.connection as connection:
            try:
                migration.apply(connection)
            except AttributeError:
                raise MigrationError('Migrations must define a forward operation (`apply()`).')
        self._insert(migration)
        if getattr(migration, '__bump_version__', False):
            self.user_version += 1

    def iter_applied_migrations(self):
        with self.connection as connection:
            for row in connection.execute('SELECT name FROM migrations'):
                yield row[0]

    def rollback(self, migration):
        with self.connection as connection:
            try:
                migration.rollback(connection)
            except AttributeError:
                raise MigrationError('Migration {} cannot be reverted.'.format(get_migration_name(migration)))
        self._delete(migration)
        if getattr(migration, '__bump_version__', False):
            self.user_version -= 1


def get_migration_name(module):
    return module.__name__.split('.')[-1]


def iter_migrations():
    from . import migrations
    for module_info in pkgutil.iter_modules(migrations.__path__):
        name = module_info[1]
        migration = get_migration(name)
        yield migration


def get_migration(name):
    return importlib.import_module('duiker.db.migrations.' + name)


def sort_migrations():
    graph = MigrationGraph(iter_migrations())
    return graph.sort()
