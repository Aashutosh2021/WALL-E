"""Fast persistent conversation memory for WALL-E.

SQLite is used instead of a giant JSON file:
- WAL mode keeps reads/writes cheap on Raspberry Pi.
- Every user/assistant/tool event is persisted.
- Recent turns can be loaded quickly for Gemini context.
- Full history remains on disk.
"""

import os
import sqlite3
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv(
    "CONVERSATION_DB",
    os.path.join(BASE, "walle_conversation.db"),
)

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


def _connect():
    """Return this thread's persistent connection, opening it once.

    BUG FIXED: `_local = threading.local()` was already declared at module
    scope but never referenced anywhere — every save_message()/
    get_recent_messages() call was opening a brand-new sqlite3 connection
    (connect + 3 PRAGMA statements) and closing it again immediately after.
    That runs on the asyncio.to_thread() hot path after every single
    user/assistant/tool turn, including every move_robot call. Reusing one
    connection per worker thread removes that connect/PRAGMA/close
    overhead from the common case. Schema, WAL mode, and all call
    signatures are unchanged.
    """
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

            CREATE INDEX IF NOT EXISTS idx_conversation_ts
                ON conversation(ts);

            CREATE INDEX IF NOT EXISTS idx_conversation_session_ts
                ON conversation(session_id, ts);
            """
        )
        conn.commit()
        # NOTE: connection is intentionally left open — it's the calling
        # thread's persistent handle now (see _connect()), not a
        # short-lived one. init_db() usually runs on the main thread at
        # startup; closing it here would poison that thread's cached
        # connection for every later call on the same thread (e.g.
        # format_recent_context() in run()).

        _initialized = True


def save_message(role, content, session_id=None,
                 tool_name=None, tool_args=None, tool_result=None):
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
        (
            time.time(),
            role,
            content or "",
            session_id,
            tool_name,
            tool_args,
            tool_result,
        ),
    )
    conn.commit()


def get_recent_messages(limit=30, session_id=None):
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


def format_recent_context(limit=30, session_id=None):
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
                lines.append(
                    f"Tool {tool_name} result: {tool_result or content}"
                )
            elif content:
                lines.append(f"Tool result: {content}")

    return "\n".join(lines)


def close():
    """Close this thread's persistent connection, if one is open.

    Connections are now thread-local and long-lived (see _connect()), so
    unlike the old short-lived-per-call design there IS something to close
    here — mainly useful for clean shutdown/tests on the calling thread.
    """
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None
