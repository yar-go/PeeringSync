import sqlite3
from typing import Optional, Tuple


class Database:
    def __init__(self, db_path: str = 'PeeringSync.db'):
        self.db_path = db_path

    @staticmethod
    def create_tables(db_path: str = 'PeeringSync.db'):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS seeds (
                    network_id BLOB,
                    timestamp INTEGER,
                    data BLOB
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS paths (
                    network_id BLOB,
                    timestamp INTEGER,
                    path TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS names (
                    network_id BLOB,
                    timestamp INTEGER,
                    name TEXT
                )
            ''')

            conn.commit()

    def insert_seed(self, id_bytes: bytes, timestamp: int, data_bytes: bytes):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO seeds (network_id, timestamp, data)
                VALUES (?, ?, ?)
            ''', (id_bytes, timestamp, data_bytes))
            conn.commit()

    def insert_path(self, id_bytes: bytes, timestamp: int, data_bytes: bytes):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO paths (network_id, timestamp, path)
                VALUES (?, ?, ?)
            ''', (id_bytes, timestamp, data_bytes))
            conn.commit()

    def get_latest_seed(self, id_bytes: bytes) -> Optional[Tuple[int, bytes]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, data
                FROM seeds
                WHERE network_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (id_bytes,))
            result = cursor.fetchone()
            return result  # (timestamp, data) or None

    def get_latest_path(self, id_bytes: bytes) -> Optional[Tuple[int, bytes]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, path
                FROM paths
                WHERE network_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (id_bytes,))
            result = cursor.fetchone()
            return result  # (timestamp, data)

    def insert_name(self, id_bytes: bytes, timestamp: int, data_bytes: bytes):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                   INSERT INTO names (network_id, timestamp, name)
                   VALUES (?, ?, ?)
               ''', (id_bytes, timestamp, data_bytes))
            conn.commit()

    def get_latest_name(self, id_bytes: bytes) -> Optional[Tuple[int, bytes]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, name
                FROM names
                WHERE network_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (id_bytes,))
            result = cursor.fetchone()
            return result  # (timestamp, data)


