import os
import sqlite3


def open_database(path: str) -> sqlite3.Connection:
    expanded_path = os.path.expanduser(path)
    parent_directory = os.path.dirname(expanded_path)
    
    if parent_directory:
        os.makedirs(parent_directory, exist_ok=True)
    
    connection = sqlite3.connect(expanded_path)
    connection.execute("PRAGMA journal_mode=WAL")
    
    connection.execute("""
        CREATE TABLE IF NOT EXISTS sync_mappings (
            linkora_id   INTEGER NOT NULL,
            readeck_uid  TEXT NOT NULL,
            url          TEXT NOT NULL,
            PRIMARY KEY (linkora_id, readeck_uid)
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_sync_mappings_url ON sync_mappings (url)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_sync_mappings_readeck ON sync_mappings (readeck_uid)")
    
    connection.execute("""
        CREATE TABLE IF NOT EXISTS tag_mappings (
            linkora_tag_id  INTEGER PRIMARY KEY,
            label_name      TEXT NOT NULL
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_tag_mappings_name ON tag_mappings (label_name)")
    
    connection.execute("""
        CREATE TABLE IF NOT EXISTS sync_state (
            key    TEXT PRIMARY KEY,
            value  TEXT NOT NULL
        )
    """)
    
    connection.commit()
    
    return connection


def get_state(connection: sqlite3.Connection, key: str) -> str | None:
    cursor = connection.execute("SELECT value FROM sync_state WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None


def set_state(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute("INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)", (key, value))
    connection.commit()


def get_mapping_by_linkora_id(connection: sqlite3.Connection, linkora_id: int) -> tuple[int, str, str] | None:
    cursor = connection.execute(
        "SELECT linkora_id, readeck_uid, url FROM sync_mappings WHERE linkora_id = ?",
        (linkora_id,)
    )
    row = cursor.fetchone()
    return tuple(row) if row else None


def get_mapping_by_readeck_uid(connection: sqlite3.Connection, readeck_uid: str) -> tuple[int, str, str] | None:
    cursor = connection.execute(
        "SELECT linkora_id, readeck_uid, url FROM sync_mappings WHERE readeck_uid = ?",
        (readeck_uid,)
    )
    row = cursor.fetchone()
    return tuple(row) if row else None


def get_mapping_by_url(connection: sqlite3.Connection, url: str) -> tuple[int, str, str] | None:
    cursor = connection.execute(
        "SELECT linkora_id, readeck_uid, url FROM sync_mappings WHERE url = ?",
        (url,)
    )
    row = cursor.fetchone()
    return tuple(row) if row else None


def add_mapping(connection: sqlite3.Connection, linkora_id: int, readeck_uid: str, url: str) -> None:
    connection.execute(
        "INSERT INTO sync_mappings (linkora_id, readeck_uid, url) VALUES (?, ?, ?)",
        (linkora_id, readeck_uid, url)
    )
    connection.commit()


def remove_mapping_by_linkora_id(connection: sqlite3.Connection, linkora_id: int) -> None:
    connection.execute("DELETE FROM sync_mappings WHERE linkora_id = ?", (linkora_id,))
    connection.commit()


def remove_mapping_by_readeck_uid(connection: sqlite3.Connection, readeck_uid: str) -> None:
    connection.execute("DELETE FROM sync_mappings WHERE readeck_uid = ?", (readeck_uid,))
    connection.commit()


def get_tag_mapping_by_id(connection: sqlite3.Connection, tag_id: int) -> str | None:
    cursor = connection.execute("SELECT label_name FROM tag_mappings WHERE linkora_tag_id = ?", (tag_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_tag_mapping_by_name(connection: sqlite3.Connection, name: str) -> int | None:
    cursor = connection.execute("SELECT linkora_tag_id FROM tag_mappings WHERE label_name = ?", (name,))
    row = cursor.fetchone()
    return row[0] if row else None


def add_tag_mapping(connection: sqlite3.Connection, tag_id: int, name: str) -> None:
    connection.execute(
        "INSERT INTO tag_mappings (linkora_tag_id, label_name) VALUES (?, ?)",
        (tag_id, name)
    )
    connection.commit()


def remove_tag_mapping_by_id(connection: sqlite3.Connection, tag_id: int) -> None:
    connection.execute("DELETE FROM tag_mappings WHERE linkora_tag_id = ?", (tag_id,))
    connection.commit()


def update_tag_mapping_name(connection: sqlite3.Connection, tag_id: int, new_name: str) -> None:
    connection.execute(
        "UPDATE tag_mappings SET label_name = ? WHERE linkora_tag_id = ?",
        (new_name, tag_id)
    )
    connection.commit()


def get_all_tag_mappings(connection: sqlite3.Connection) -> list[tuple[int, str]]:
    cursor = connection.execute("SELECT linkora_tag_id, label_name FROM tag_mappings")
    return [tuple(row) for row in cursor.fetchall()]
