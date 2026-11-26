"""
What the SQLite databases of bup (the backup history and the AWS price cache) have in common: where the database is, and how it is
opened.
"""

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Generator


class SQLiteStore:
    """
    A SQLite database file. Every use opens a connection of its own and closes it again, so a store can be used from any thread
    (the backups each run in their own), and by more than one bup at a time. A derived class makes its tables in its __init__().
    """

    def __init__(self, path: Path):
        """
        :param path: the path of the database (its directory is made if it does not exist, and SQLite makes the file)
        """
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection]:
        """
        A connection to the database for reading, which is closed when the block is left. Nothing is committed.
        """
        with closing(sqlite3.connect(self.path)) as connection:
            yield connection

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """
        A connection to the database for writing: what the block does is committed when the block is left, or rolled back if it
        raises, and the connection is then closed.
        """
        with self.connection() as connection, connection:
            yield connection
