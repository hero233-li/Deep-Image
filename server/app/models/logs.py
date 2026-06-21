"""请求日志 —— 记录每次 API 调用的成功/失败"""

import json
import uuid
from datetime import datetime, timezone
from app.models.database import get_db


async def init_logs_table():
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS request_logs (
            id TEXT PRIMARY KEY,
            endpoint TEXT NOT NULL,
            model_name TEXT NOT NULL DEFAULT '',
            mode TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'ok',
            duration_ms INTEGER DEFAULT 0,
            request_summary TEXT DEFAULT '',
            response_summary TEXT DEFAULT '',
            error_detail TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_logs_created ON request_logs(created_at DESC);
    """)
    await db.commit()
    await db.close()


async def add_log(
    endpoint: str,
    model_name: str = "",
    mode: str = "",
    status: str = "ok",
    duration_ms: int = 0,
    request_summary: str = "",
    response_summary: str = "",
    error_detail: str = "",
):
    db = await get_db()
    log_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO request_logs (id, endpoint, model_name, mode, status, duration_ms, request_summary, response_summary, error_detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (log_id, endpoint, model_name, mode, status, duration_ms, request_summary[:500], response_summary[:500], error_detail[:1000], now),
    )
    await db.commit()
    await db.close()
    return log_id


async def list_logs(limit: int = 50) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM request_logs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]
