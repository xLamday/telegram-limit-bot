"""
Layer database — SQLite thread-safe con WAL mode.
"""

import sqlite3
import threading
import time
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("antispam.db")


class Database:
    def __init__(self, path: str):
        self._path = path
        self._local = threading.local()
        self._init_schema()
        logger.info(f"Database inizializzato: {path}")

    # ── Connessione ─────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """Restituisce la connessione thread-locale, creandola se necessario."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    # ── Schema ───────────────────────────────────────────────────────────────

    def _init_schema(self):
        with self._cursor() as cur:
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS groups (
                    group_id      INTEGER PRIMARY KEY,
                    group_name    TEXT,
                    registered_at INTEGER DEFAULT (strftime('%s','now'))
                );

                CREATE TABLE IF NOT EXISTS users (
                    group_id   INTEGER NOT NULL,
                    user_id    INTEGER NOT NULL,
                    status     TEXT    NOT NULL DEFAULT 'limited',
                    updated_at INTEGER DEFAULT (strftime('%s','now')),
                    PRIMARY KEY (group_id, user_id),
                    FOREIGN KEY (group_id) REFERENCES groups(group_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_users_status
                    ON users(group_id, status);
            """)

    # ── Gruppi ───────────────────────────────────────────────────────────────

    def upsert_group(self, group_id: int, group_name: str):
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO groups (group_id, group_name) VALUES (?,?)",
                (group_id, group_name),
            )
        logger.debug(f"Gruppo upserted: {group_id} ({group_name})")

    def list_groups(self) -> list:
        with self._cursor() as cur:
            cur.execute("SELECT group_id, group_name, registered_at FROM groups")
            return cur.fetchall()

    def group_exists(self, group_id: int) -> bool:
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM groups WHERE group_id=?", (group_id,))
            return cur.fetchone() is not None

    # ── Utenti ───────────────────────────────────────────────────────────────

    def set_user(self, group_id: int, user_id: int, status: str):
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO users (group_id, user_id, status, updated_at)
                   VALUES (?,?,?,strftime('%s','now'))
                   ON CONFLICT(group_id, user_id) DO UPDATE SET
                       status=excluded.status,
                       updated_at=excluded.updated_at""",
                (group_id, user_id, status),
            )
        logger.debug(f"Utente {user_id} in gruppo {group_id} → {status}")

    def bulk_set_admins(self, group_id: int, admin_ids: list[int]):
        """Registra una lista di admin in un'unica transazione.
        Non sovrascrive chi era già 'free' (privilegio più alto)."""
        with self._cursor() as cur:
            cur.executemany(
                """INSERT INTO users (group_id, user_id, status, updated_at)
                   VALUES (?,?,'admin',strftime('%s','now'))
                   ON CONFLICT(group_id, user_id) DO UPDATE SET
                       status = CASE WHEN status = 'free' THEN 'free' ELSE 'admin' END,
                       updated_at = strftime('%s','now')""",
                [(group_id, uid) for uid in admin_ids],
            )
        logger.debug(f"Gruppo {group_id}: {len(admin_ids)} admin salvati nel DB.")

    def get_user_status(self, group_id: int, user_id: int) -> Optional[str]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT status FROM users WHERE group_id=? AND user_id=?",
                (group_id, user_id),
            )
            row = cur.fetchone()
            return row["status"] if row else None

    def list_users(self, group_id: int) -> list:
        with self._cursor() as cur:
            cur.execute(
                "SELECT user_id, status, updated_at FROM users WHERE group_id=?",
                (group_id,),
            )
            return cur.fetchall()
