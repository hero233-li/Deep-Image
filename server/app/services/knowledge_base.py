"""
向量知识库：BGE-M3 + ChromaDB
PDF 提取→分题→向量化→检索，全部本地运行
"""

import os
import re
import hashlib
import asyncio
from pathlib import Path
from app.config import BASE_DIR
from app.utils.logger import logger

KB_DIR = BASE_DIR / "kb_store"
KB_DIR.mkdir(exist_ok=True)

_embedder = None
_collection = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("KB_EMBED_MODEL", "BAAI/bge-m3")
        logger.info("Loading embedding model %s ...", model_name)
        _embedder = SentenceTransformer(model_name)
    return _embedder


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb
        client = chromadb.PersistentClient(path=str(KB_DIR))
        _collection = client.get_or_create_collection(
            name="exam_questions",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def extract_questions_from_pdf(file_path: str) -> list[dict]:
    """从 PDF 中按题目边界切分，返回 [{text, page, index}]"""
    import fitz  # pymupdf

    doc = fitz.open(file_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"

    # 按题目分隔符切分
    # 考研题目标记：例、例题、第X题、(X)、数字+点 等
    chunks = re.split(
        r'\n(?=(?:例\s*\d+|例题\s*\d+|第\s*\d+\s*题|\d+[\.\、]\s*(?:设|已|如|若|在|函|求|证|解|计|判|选)\b))',
        full_text
    )

    questions = []
    for i, chunk in enumerate(chunks):
        text = chunk.strip()
        if len(text) < 30:  # 太短的跳过（目录、页码等）
            continue
        questions.append({
            "text": text[:3000],  # 截断超长文本
            "index": i,
        })

    logger.info("Extracted %d questions from PDF (%d raw chunks)", len(questions), len(chunks))
    return questions


def index_questions(questions: list[dict], subject: str = "", source: str = "") -> int:
    """将题目列表向量化并存入 ChromaDB，返回入库数量"""
    if not questions:
        return 0

    model = _get_embedder()
    collection = _get_collection()

    texts = [q["text"] for q in questions]

    # 批量 embedding（BGE-M3 自带指令前缀优化）
    logger.info("Embedding %d questions...", len(texts))
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    # 生成 ID 和 metadata
    ids = []
    metadatas = []
    for i, q in enumerate(questions):
        hash_id = hashlib.md5(q["text"][:200].encode()).hexdigest()[:16]
        ids.append(f"{subject}_{hash_id}_{i}")
        metadatas.append({
            "subject": subject,
            "source": source,
            "char_count": len(q["text"]),
            "text_preview": q["text"][:200],
        })

    # 分批写入
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[i:i+batch_size],
            embeddings=embeddings[i:i+batch_size].tolist(),
            documents=texts[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size],
        )

    logger.info("Indexed %d questions to ChromaDB", len(ids))
    return len(ids)


def search_similar(text: str, top_k: int = 5, subject: str = "") -> list[dict]:
    """搜索最相似的题目"""
    model = _get_embedder()
    collection = _get_collection()

    query_embedding = model.encode(
        [text],
        normalize_embeddings=True,
    )

    where = None
    if subject:
        where = {"subject": subject}

    results = collection.query(
        query_embeddings=query_embedding.tolist(),
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    matches = []
    if results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            matches.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "score": 1 - results["distances"][0][i],  # cosine → similarity
            })

    return matches


def search_by_image_text(vision_result: str, subject: str = "", top_k: int = 5) -> list[dict]:
    """用豆包识别结果搜索知识库"""
    return search_similar(vision_result, top_k, subject)


def get_kb_stats() -> dict:
    """获取知识库统计"""
    collection = _get_collection()
    count = collection.count()
    return {
        "total_questions": count,
        "store_path": str(KB_DIR),
    }


def delete_kb():
    """清空知识库"""
    import chromadb
    client = chromadb.PersistentClient(path=str(KB_DIR))
    try:
        client.delete_collection("exam_questions")
    except Exception:
        pass
    global _collection
    _collection = None
    _get_collection()  # re-create
    logger.info("Knowledge base cleared")
