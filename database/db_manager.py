import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional

from config import DB_PATH
from database.models import SCHEMA_SQL, VALID_ACTIONS, VALID_STATUSES

_lock = threading.Lock()


class DatabaseManager:
    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or DB_PATH)
        self._local = threading.local()
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = self._connect()
        return self._local.conn

    @contextmanager
    def transaction(self):
        with _lock:
            conn = self.conn
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def init_schema(self):
        with self.transaction() as conn:
            conn.executescript(SCHEMA_SQL)

    def add_topic(self, name: str, keywords: List[str], sources: List[str],
                  interval_minutes: int = 60, enabled: bool = True) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO Topics (name, keywords, sources, interval_minutes, enabled) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, json.dumps(keywords, ensure_ascii=False),
                 json.dumps(sources, ensure_ascii=False),
                 interval_minutes, 1 if enabled else 0),
            )
            return cur.lastrowid

    def update_topic(self, topic_id: int, name: str = None, keywords: List[str] = None,
                     sources: List[str] = None, interval_minutes: int = None,
                     enabled: bool = None):
        fields: Dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if keywords is not None:
            fields["keywords"] = json.dumps(keywords, ensure_ascii=False)
        if sources is not None:
            fields["sources"] = json.dumps(sources, ensure_ascii=False)
        if interval_minutes is not None:
            fields["interval_minutes"] = interval_minutes
        if enabled is not None:
            fields["enabled"] = 1 if enabled else 0
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [topic_id]
        with self.transaction() as conn:
            conn.execute(f"UPDATE Topics SET {set_clause} WHERE id = ?", params)

    def delete_topic(self, topic_id: int):
        with self.transaction() as conn:
            conn.execute("DELETE FROM Topics WHERE id = ?", (topic_id,))

    def get_topic(self, topic_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM Topics WHERE id = ?", (topic_id,)).fetchone()
        return self._topic_row_to_dict(row) if row else None

    def get_all_topics(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM Topics"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY id"
        rows = self.conn.execute(sql).fetchall()
        return [self._topic_row_to_dict(r) for r in rows]

    @staticmethod
    def _topic_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "keywords": json.loads(row["keywords"]),
            "sources": json.loads(row["sources"]),
            "interval_minutes": row["interval_minutes"],
            "enabled": bool(row["enabled"]),
            "last_fetched_at": row["last_fetched_at"],
            "created_at": row["created_at"],
        }

    def add_article(self, article: Dict[str, Any]) -> Optional[int]:
        with self.transaction() as conn:
            exists = conn.execute(
                "SELECT id FROM Articles WHERE url = ? AND topic_id = ?",
                (article["url"], article["topic_id"]),
            ).fetchone()
            if exists:
                return None
            cur = conn.execute(
                "INSERT INTO Articles "
                "(topic_id, title, url, source, author, summary, content, "
                " published_at, simhash, relevance_score, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    article["topic_id"], article["title"], article["url"],
                    article["source"], article.get("author"),
                    article.get("summary"), article.get("content"),
                    article.get("published_at"), article.get("simhash"),
                    article.get("relevance_score", 0.0), "unread",
                ),
            )
            return cur.lastrowid

    def article_exists_by_simhash(self, simhash: str, hamming_distance: int = 3) -> bool:
        rows = self.conn.execute(
            "SELECT simhash FROM Articles WHERE simhash IS NOT NULL"
        ).fetchall()
        from processors.simhash import Simhash
        for r in rows:
            if Simhash.hamming_distance(simhash, r["simhash"]) <= hamming_distance:
                return True
        return False

    def get_articles(self, topic_id: Optional[int] = None,
                     status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM Articles WHERE 1=1"
        params: List[Any] = []
        if topic_id is not None:
            sql += " AND topic_id = ?"
            params.append(topic_id)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY fetched_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_article(self, article_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM Articles WHERE id = ?", (article_id,)).fetchone()
        return dict(row) if row else None

    def set_article_status(self, article_id: int, status: str):
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        with self.transaction() as conn:
            conn.execute("UPDATE Articles SET status = ? WHERE id = ?", (status, article_id))

    def record_action(self, article_id: int, action: str):
        if action not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {action}")
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO UserActions (article_id, action) VALUES (?, ?)",
                (article_id, action),
            )

    def update_topic_fetched(self, topic_id: int, timestamp: str):
        with self.transaction() as conn:
            conn.execute(
                "UPDATE Topics SET last_fetched_at = ? WHERE id = ?",
                (timestamp, topic_id),
            )

    def search_similar_simhash(self, simhash: str, hamming_distance: int = 3) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM Articles WHERE simhash IS NOT NULL"
        ).fetchall()
        from processors.simhash import Simhash
        result: List[Dict[str, Any]] = []
        for r in rows:
            if Simhash.hamming_distance(simhash, r["simhash"]) <= hamming_distance:
                result.append(dict(r))
        return result

    def count_articles(self, topic_id: Optional[int] = None) -> int:
        if topic_id is not None:
            row = self.conn.execute(
                "SELECT COUNT(*) AS c FROM Articles WHERE topic_id = ?", (topic_id,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) AS c FROM Articles").fetchone()
        return row["c"]

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
