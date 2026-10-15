"""Fast persistent conversation memory for WALL-E."""

import os
import json
import sqlite3
import threading
import time
import logging

logger = logging.getLogger(__name__)

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")
MAX_RECENT_TURNS = 8   # Keep only last 8 turns to prevent token slowdown
MAX_FACTS = 15         # Cap stored user facts


def load_memory() -> dict:
    if not os.path.exists(MEMORY_FILE):
        return {"facts": [], "recent_conversations": []}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"facts": [], "recent_conversations": []}
            return data
    except Exception as e:
        logger.warning(f"Failed to read memory.json: {e}")
        return {"facts": [], "recent_conversations": []}


def save_memory(data: dict) -> None:
    try:
        if "facts" in data:
            data["facts"] = data["facts"][-MAX_FACTS:]
        if "recent_conversations" in data:
            data["recent_conversations"] = data["recent_conversations"][-MAX_RECENT_TURNS:]
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to save memory.json: {e}")


DB_PATH = os.getenv(
    "CONVERSATION_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "walle_conversation.db"),
)

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


def _connect():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn

    conn = sqlite3.connect(
        DB_PATH,
        timeout=5.0,
        check_same_thread=False,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    _local.conn = conn
    return conn


def init_db():
    global _initialized
    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return

        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        conn = _connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                session_id TEXT,
                tool_name TEXT,
                tool_args TEXT,
                tool_result TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_conversation_ts ON conversation(ts);
            CREATE INDEX IF NOT EXISTS idx_conversation_session_ts ON conversation(session_id, ts);
            """
        )
        conn.commit()
        _initialized = True


def save_message(role, content, session_id=None, tool_name=None, tool_args=None, tool_result=None):
    if not content and not tool_name:
        return
    init_db()
    conn = _connect()
    conn.execute(
        """
        INSERT INTO conversation
        (ts, role, content, session_id, tool_name, tool_args, tool_result)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (time.time(), role, content or "", session_id, tool_name, tool_args, tool_result),
    )
    conn.commit()


def get_recent_messages(limit=MAX_RECENT_TURNS, session_id=None):
    init_db()
    conn = _connect()
    if session_id:
        rows = conn.execute(
            """
            SELECT role, content, tool_name, tool_result
            FROM conversation
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT role, content, tool_name, tool_result
            FROM conversation
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    rows.reverse()
    return rows


def format_recent_context(limit=MAX_RECENT_TURNS, session_id=None):
    rows = get_recent_messages(limit, session_id)
    if not rows:
        return ""
    lines = ["RECENT WALL-E CONVERSATION:"]
    for role, content, tool_name, tool_result in rows:
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            lines.append(f"WALL-E: {content}")
        elif role == "tool":
            if tool_name:
                lines.append(f"Tool {tool_name} result: {tool_result or content}")
            elif content:
                lines.append(f"Tool result: {content}")
    return "\n".join(lines)


def close():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None
