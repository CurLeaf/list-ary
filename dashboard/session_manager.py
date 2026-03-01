import asyncio
import sqlite3
import os
import sys
import threading
import uuid
import json
from datetime import datetime, timezone, timedelta

from utils import get_data_dir

DB_PATH = os.path.join(get_data_dir(), "dashboard.db")
STUCK_TIMEOUT_MINUTES = 5

_local = threading.local()


def _ensure_data_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    """线程级 SQLite 连接复用"""
    if not hasattr(_local, "conn") or _local.conn is None:
        _ensure_data_dir()
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return _local.conn


def init_db():
    """初始化 SQLite 数据库"""
    _ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            task TEXT DEFAULT '',
            previous_request TEXT DEFAULT '',
            status TEXT DEFAULT 'executing',
            questions TEXT DEFAULT '[]',
            timestamp TEXT DEFAULT '',
            last_active TEXT DEFAULT '',
            reply TEXT DEFAULT NULL,
            reply_timestamp TEXT DEFAULT NULL,
            task_id INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_counter (
            id INTEGER PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
    """)
    cursor = conn.execute("SELECT count FROM task_counter WHERE id = 1")
    if cursor.fetchone() is None:
        conn.execute("INSERT INTO task_counter (id, count) VALUES (1, 0)")
    conn.commit()
    conn.close()


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def _next_task_id() -> int:
    conn = _get_conn()
    conn.execute("UPDATE task_counter SET count = count + 1 WHERE id = 1")
    cursor = conn.execute("SELECT count FROM task_counter WHERE id = 1")
    task_id = cursor.fetchone()[0]
    conn.commit()
    return task_id


def generate_session_id() -> str:
    return f"ws-{uuid.uuid4().hex[:6]}"


def create_or_update_session(
    session_id: str | None,
    project: str,
    task: str,
    previous_request: str,
    status: str,
    questions: list[str],
    timestamp: str,
) -> tuple[str, int]:
    """创建或更新会话，返回 (session_id, task_id)"""
    conn = _get_conn()
    now = _now_iso()
    task_id = _next_task_id()

    if not timestamp:
        timestamp = now

    # 映射 status 到会话状态
    if status == "need_confirm":
        session_status = "need_confirm"
    elif status == "blocked":
        session_status = "blocked"
    elif status == "completed":
        session_status = "completed"
    else:
        session_status = "waiting"

    if session_id:
        # 更新已有会话
        cursor = conn.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
        if cursor.fetchone():
            conn.execute("""
                UPDATE sessions SET
                    project = ?, task = ?, previous_request = ?, status = ?,
                    questions = ?, timestamp = ?, last_active = ?,
                    reply = NULL, reply_timestamp = NULL, task_id = ?
                WHERE session_id = ?
            """, (project, task, previous_request, session_status,
                  json.dumps(questions, ensure_ascii=False), timestamp, now, task_id, session_id))
            conn.commit()
            return session_id, task_id

    # 创建新会话
    if not session_id:
        session_id = generate_session_id()

    conn.execute("""
        INSERT INTO sessions (session_id, project, task, previous_request, status, questions, timestamp, last_active, task_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, project, task, previous_request, session_status,
          json.dumps(questions, ensure_ascii=False), timestamp, now, task_id))
    conn.commit()
    return session_id, task_id


def set_reply(session_id: str, reply: str) -> bool:
    """设置会话的回复"""
    conn = _get_conn()
    now = _now_iso()
    new_status = "cancelled" if reply == "[CANCEL]" else "executing"
    cursor = conn.execute("""
        UPDATE sessions SET reply = ?, reply_timestamp = ?, status = ?
        WHERE session_id = ?
    """, (reply, now, new_status, session_id))
    updated = cursor.rowcount > 0
    conn.commit()
    return updated


def get_reply(session_id: str) -> str | None:
    """获取会话的回复（供长轮询使用）"""
    conn = _get_conn()
    cursor = conn.execute("SELECT reply FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return row[0]
    return None


def get_session(session_id: str) -> dict | None:
    """获取单个会话"""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    if row:
        return _row_to_dict(row)
    return None


def get_all_sessions() -> list[dict]:
    """获取所有活跃会话"""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM sessions ORDER BY last_active DESC")
    rows = cursor.fetchall()
    return [_row_to_dict(row) for row in rows]


def update_session_status(session_id: str, status: str) -> bool:
    """更新会话状态（标记正常/卡死等）"""
    conn = _get_conn()
    now = _now_iso()
    updates = {"status": status}
    if status == "executing":
        updates["last_active"] = now
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [session_id]
    cursor = conn.execute(f"UPDATE sessions SET {set_clause} WHERE session_id = ?", values)
    updated = cursor.rowcount > 0
    conn.commit()
    return updated


def delete_session(session_id: str) -> bool:
    """删除会话"""
    conn = _get_conn()
    cursor = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    return deleted


def clean_all_sessions() -> int:
    """清理所有会话，返回删除数量"""
    conn = _get_conn()
    cursor = conn.execute("DELETE FROM sessions")
    count = cursor.rowcount
    conn.execute("UPDATE task_counter SET count = 0 WHERE id = 1")
    conn.commit()
    return count


def get_session_context(session_id: str) -> str:
    """获取会话历史摘要文本，用于复制上下文"""
    session = get_session(session_id)
    if not session:
        return ""
    lines = [
        f"项目: {session['project']}",
        f"会话: {session['session_id']}",
        f"最近任务: {session['task']}",
        f"上一需求: {session['previous_request']}",
        f"状态: {session['status']}",
    ]
    questions = session.get("questions", [])
    if isinstance(questions, str):
        questions = json.loads(questions)
    if questions:
        lines.append(f"疑问: {'; '.join(questions)}")
    if session.get("reply"):
        lines.append(f"回复: {session['reply']}")
    return "\n".join(lines)


def check_stuck_sessions() -> list[str]:
    """检查超时会话，标记为 stuck，返回被标记的 session_id 列表"""
    conn = _get_conn()
    threshold = (datetime.now(timezone(timedelta(hours=8))) - timedelta(minutes=STUCK_TIMEOUT_MINUTES)).isoformat()
    cursor = conn.execute("""
        SELECT session_id FROM sessions
        WHERE status = 'executing' AND last_active < ? AND last_active != ''
    """, (threshold,))
    stuck_ids = [row[0] for row in cursor.fetchall()]
    if stuck_ids:
        placeholders = ",".join("?" * len(stuck_ids))
        conn.execute(f"UPDATE sessions SET status = 'stuck' WHERE session_id IN ({placeholders})", stuck_ids)
        conn.commit()
    return stuck_ids


def _row_to_dict(row) -> dict:
    d = dict(row)
    if isinstance(d.get("questions"), str):
        try:
            d["questions"] = json.loads(d["questions"])
        except (json.JSONDecodeError, TypeError):
            d["questions"] = []
    return d


# 长轮询用的事件管理
_reply_events: dict[str, asyncio.Event] = {}


def get_reply_event(session_id: str) -> asyncio.Event:
    """获取或创建长轮询用的 asyncio.Event"""
    if session_id not in _reply_events:
        _reply_events[session_id] = asyncio.Event()
    return _reply_events[session_id]


def notify_reply(session_id: str):
    """通知长轮询有新回复"""
    if session_id in _reply_events:
        _reply_events[session_id].set()


def clear_reply_event(session_id: str):
    """清除事件状态"""
    if session_id in _reply_events:
        _reply_events[session_id].clear()


def remove_reply_event(session_id: str):
    """移除事件"""
    _reply_events.pop(session_id, None)


def clean_expired_sessions(expire_days: int = 7) -> int:
    """清理 N 天前的已完成/已取消会话，返回清理数量"""
    conn = _get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=expire_days)).isoformat()
    cursor = conn.execute(
        "DELETE FROM sessions WHERE status IN ('completed', 'cancelled') AND last_active < ?",
        (cutoff,)
    )
    cleaned = cursor.rowcount
    conn.commit()
    return cleaned
