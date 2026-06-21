import uuid
import aiosqlite
from datetime import datetime, timezone
from app.config import DATABASE_PATH


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DATABASE_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS analysis_records (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            image_path TEXT NOT NULL,
            model_name TEXT NOT NULL,
            mode TEXT DEFAULT 'code',
            user_question TEXT DEFAULT '',
            vision_result TEXT,
            analysis_result TEXT,
            status TEXT DEFAULT 'pending',
            from_cache INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS image_cache (
            image_hash TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            vision_result TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS analysis_cache (
            cache_key TEXT PRIMARY KEY,
            analysis_result TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    await db.commit()
    await db.close()


# ---- Image Cache ----

async def get_cached_vision(db: aiosqlite.Connection, image_hash: str, model_name: str) -> str | None:
    cursor = await db.execute(
        "SELECT vision_result FROM image_cache WHERE image_hash=? AND model_name=? ORDER BY created_at DESC LIMIT 1",
        (image_hash, model_name),
    )
    row = await cursor.fetchone()
    return row["vision_result"] if row else None


async def set_cached_vision(db: aiosqlite.Connection, image_hash: str, model_name: str, vision_result: str):
    await db.execute(
        "INSERT OR REPLACE INTO image_cache (image_hash, model_name, vision_result, created_at) VALUES (?, ?, ?, ?)",
        (image_hash, model_name, vision_result, datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()


# ---- Analysis Cache ----

async def get_cached_analysis(db: aiosqlite.Connection, cache_key: str) -> str | None:
    cursor = await db.execute(
        "SELECT analysis_result FROM analysis_cache WHERE cache_key=? ORDER BY created_at DESC LIMIT 1",
        (cache_key,),
    )
    row = await cursor.fetchone()
    return row["analysis_result"] if row else None


async def set_cached_analysis(db: aiosqlite.Connection, cache_key: str, analysis_result: str):
    await db.execute(
        "INSERT OR REPLACE INTO analysis_cache (cache_key, analysis_result, created_at) VALUES (?, ?, ?)",
        (cache_key, analysis_result, datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()


async def create_record(
    db: aiosqlite.Connection,
    filename: str,
    image_path: str,
    model_name: str,
    mode: str = "code",
    user_question: str = "",
    from_cache: bool = False,
) -> str:
    record_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO analysis_records (id, filename, image_path, model_name, mode, user_question, from_cache, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (record_id, filename, image_path, model_name, mode, user_question, int(from_cache), now),
    )
    await db.commit()
    return record_id


async def update_record(
    db: aiosqlite.Connection,
    record_id: str,
    vision_result: str,
    analysis_result: str,
    status: str = "completed",
    from_cache: bool = False,
):
    await db.execute(
        "UPDATE analysis_records SET vision_result=?, analysis_result=?, status=?, from_cache=? WHERE id=?",
        (vision_result, analysis_result, status, int(from_cache), record_id),
    )
    await db.commit()


async def get_record(db: aiosqlite.Connection, record_id: str) -> dict | None:
    cursor = await db.execute("SELECT * FROM analysis_records WHERE id=?", (record_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def list_records(db: aiosqlite.Connection, limit: int = 20, offset: int = 0) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM analysis_records ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
