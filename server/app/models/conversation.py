"""对话线程管理 + 学科知识库"""

import json
import uuid
import base64
from datetime import datetime, timezone
from app.models.database import get_db
from app.config import UPLOAD_DIR
from app.services.image_service import compute_image_hash, image_to_base64
from app.utils.logger import logger


async def init_conversations_table():
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            image_hash TEXT,
            image_base64 TEXT NOT NULL DEFAULT '',
            mode TEXT NOT NULL DEFAULT 'exam',
            subject TEXT NOT NULL DEFAULT '',
            vision_result TEXT NOT NULL DEFAULT '',
            messages TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subject_notes (
            subject TEXT PRIMARY KEY,
            mode TEXT NOT NULL DEFAULT 'exam',
            summary TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
    """)
    cursor = await db.execute("PRAGMA table_info(conversations)")
    columns = {row["name"] for row in await cursor.fetchall()}
    if "image_base64" not in columns:
        await db.execute("ALTER TABLE conversations ADD COLUMN image_base64 TEXT NOT NULL DEFAULT ''")
    if "reconstructed" not in columns:
        await db.execute("ALTER TABLE conversations ADD COLUMN reconstructed TEXT NOT NULL DEFAULT ''")
    await db.commit()
    await db.close()
    await backfill_conversation_images()


async def backfill_conversation_images():
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, image_hash FROM conversations WHERE COALESCE(image_base64, '')='' AND COALESCE(image_hash, '')!=''"
    )
    rows = await cursor.fetchall()
    if not rows:
        await db.close()
        return

    image_map: dict[str, str] = {}
    for path in UPLOAD_DIR.glob("*"):
        if not path.is_file():
            continue
        try:
            b64 = image_to_base64(str(path))
            image_map.setdefault(compute_image_hash(b64), b64)
            raw_b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
            image_map.setdefault(compute_image_hash(raw_b64), b64)
        except Exception:
            continue

    filled = 0
    for row in rows:
        b64 = image_map.get(row["image_hash"])
        if not b64:
            continue
        await db.execute(
            "UPDATE conversations SET image_base64=? WHERE id=?",
            (b64, row["id"]),
        )
        filled += 1
    await db.commit()
    await db.close()
    if filled:
        logger.info("Backfilled %d conversation images from uploads", filled)


# ---- Conversations ----

async def create_conversation(
    image_hash: str = "",
    image_base64: str = "",
    vision_result: str = "",
    mode: str = "exam",
    subject: str = "",
) -> str:
    conv_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    await db.execute(
        "INSERT INTO conversations (id, image_hash, image_base64, mode, subject, vision_result, messages, created_at) VALUES (?, ?, ?, ?, ?, ?, '[]', ?)",
        (conv_id, image_hash, image_base64, mode, subject, vision_result, now),
    )
    await db.commit()
    await db.close()
    logger.info("Conversation %s created, mode=%s subject=%s", conv_id, mode, subject)
    return conv_id


async def get_conversation(conv_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM conversations WHERE id=?", (conv_id,))
    row = await cursor.fetchone()
    await db.close()
    if not row:
        return None
    d = dict(row)
    d["messages"] = json.loads(d["messages"])
    return d


async def find_conversation_by_image(image_hash: str, mode: str = "exam", subject: str = "") -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT * FROM conversations
        WHERE image_hash=? AND mode=?
        ORDER BY
            CASE
                WHEN COALESCE(subject, '')=? THEN 0
                WHEN COALESCE(subject, '')='' THEN 1
                ELSE 2
            END,
            created_at DESC
        LIMIT 1
        """,
        (image_hash, mode, subject or ""),
    )
    row = await cursor.fetchone()
    await db.close()
    if not row:
        return None
    d = dict(row)
    d["messages"] = json.loads(d["messages"])
    return d


async def update_conversation_vision(conv_id: str, vision_result: str):
    db = await get_db()
    await db.execute(
        "UPDATE conversations SET vision_result=? WHERE id=?",
        (vision_result, conv_id),
    )
    await db.commit()
    await db.close()


async def update_conversation_image(conv_id: str, image_base64: str):
    db = await get_db()
    await db.execute(
        "UPDATE conversations SET image_base64=? WHERE id=?",
        (image_base64, conv_id),
    )
    await db.commit()
    await db.close()


async def append_message(conv_id: str, role: str, content: str):
    db = await get_db()
    cursor = await db.execute("SELECT messages FROM conversations WHERE id=?", (conv_id,))
    row = await cursor.fetchone()
    if not row:
        await db.close()
        return
    messages = json.loads(row["messages"])
    messages.append({"role": role, "content": content})
    await db.execute(
        "UPDATE conversations SET messages=? WHERE id=?",
        (json.dumps(messages, ensure_ascii=False), conv_id),
    )
    await db.commit()
    await db.close()


async def list_conversations(limit: int = 50) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, image_hash, mode, subject, created_at FROM conversations ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    await db.close()

    result = []
    seen = set()
    for r in rows:
        d = dict(r)
        dedupe_key = (d.get("mode") or "", d.get("image_hash") or d.get("id"))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        # 获取预览：第一条 user 消息的前 40 个字
        preview = ""
        msgs = json.loads(d.get("messages", "[]") or "[]")
        for m in msgs:
            if m.get("role") == "user":
                preview = m["content"][:40]
                break
        d["preview"] = preview
        d["message_count"] = len(msgs)
        result.append(d)
    return result


async def save_reconstructed(conv_id: str, reconstructed: str):
    db = await get_db()
    await db.execute(
        "UPDATE conversations SET reconstructed=? WHERE id=?",
        (reconstructed, conv_id),
    )
    await db.commit()
    await db.close()


async def update_conversation_subject(conv_id: str, subject: str):
    db = await get_db()
    await db.execute("UPDATE conversations SET subject=? WHERE id=?", (subject, conv_id))
    await db.commit()
    await db.close()


# ---- Subject Knowledge Base ----

async def get_subject_note(subject: str, mode: str = "exam") -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM subject_notes WHERE subject=? AND mode=?",
        (subject, mode),
    )
    row = await cursor.fetchone()
    await db.close()
    return dict(row) if row else None


async def update_subject_note(subject: str, mode: str, summary: str):
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    cursor = await db.execute(
        "SELECT subject FROM subject_notes WHERE subject=? AND mode=?",
        (subject, mode),
    )
    row = await cursor.fetchone()
    if row:
        await db.execute(
            "UPDATE subject_notes SET summary=?, updated_at=? WHERE subject=? AND mode=?",
            (summary, now, subject, mode),
        )
    else:
        await db.execute(
            "INSERT OR REPLACE INTO subject_notes (subject, mode, summary, updated_at) VALUES (?, ?, ?, ?)",
            (subject, mode, summary, now),
        )
    await db.commit()
    await db.close()


async def list_subjects(mode: str = "exam") -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT subject, mode, summary, updated_at FROM subject_notes WHERE mode=? ORDER BY updated_at DESC",
        (mode,),
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]
