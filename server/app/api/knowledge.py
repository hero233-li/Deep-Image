"""知识库 API"""

import os
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from app.services import knowledge_base as kb
from app.utils.logger import logger

router = APIRouter()
KB_UPLOAD_DIR = kb.KB_DIR / "pdfs"
KB_UPLOAD_DIR.mkdir(exist_ok=True)


class SearchRequest(BaseModel):
    text: str
    subject: str = ""
    top_k: int = 5
    use_rerank: bool = True


@router.post("/kb/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), subject: str = Form("考研数学")):
    """上传 PDF 并自动提取 + 向量化入库"""
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(400, "仅支持 PDF 文件")

    # 保存 PDF
    pdf_path = KB_UPLOAD_DIR / file.filename
    content = await file.read()
    pdf_path.write_bytes(content)
    logger.info("PDF saved: %s (%.1f MB)", file.filename, len(content) / 1024 / 1024)

    # 提取题目
    questions = kb.extract_questions_from_pdf(str(pdf_path))
    if not questions:
        raise HTTPException(400, "未能从 PDF 中提取到题目，请检查文件内容")

    # 向量化入库
    count = kb.index_questions(questions, subject=subject, source=file.filename)

    return {
        "filename": file.filename,
        "size_mb": round(len(content) / 1024 / 1024, 2),
        "questions_extracted": len(questions),
        "questions_indexed": count,
        "subject": subject,
    }


@router.post("/kb/search")
async def search_kb(req: SearchRequest):
    """用文本搜索知识库中的相似题目"""
    matches = kb.search_similar(req.text, req.top_k, req.subject, req.use_rerank)
    return {"matches": matches, "query": req.text[:200], "rerank": req.use_rerank}


@router.get("/kb/stats")
async def kb_stats():
    return kb.get_kb_stats()


@router.delete("/kb")
async def clear_kb():
    kb.delete_kb()
    return {"ok": True}
