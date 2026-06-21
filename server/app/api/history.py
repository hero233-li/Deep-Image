from fastapi import APIRouter
from app.models import database as db

router = APIRouter()


@router.get("/history")
async def get_history(limit: int = 20, offset: int = 0):
    db_conn = await db.get_db()
    records = await db.list_records(db_conn, limit, offset)
    await db_conn.close()
    return {"records": records, "limit": limit, "offset": offset}


@router.get("/history/{record_id}")
async def get_record_detail(record_id: str):
    db_conn = await db.get_db()
    record = await db.get_record(db_conn, record_id)
    await db_conn.close()
    if not record:
        from fastapi import HTTPException
        raise HTTPException(404, "Record not found")
    return record
