from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from app.engine.router import ModelRouter
from app.services.analysis_service import AnalysisService
from app.services.image_service import compute_image_hash
from app.services.graph_renderer import parse_graph_json, render_to_base64 as render_graph
from app.config import ANALYSIS_MODES
from app.models import database as db
from app.models import conversation as conv
from app.models import logs
from app.utils.logger import logger
import time
import json

router = APIRouter()


# ---- Request/Response ----

class VisionRequest(BaseModel):
    image_base64: str
    model_name: str = "doubao"
    mode: str = "exam"
    subject: str = ""
    force_refresh: bool = False


class ChatRequest(BaseModel):
    user_question: str
    conversation_id: str = ""
    mode: str = "exam"
    subject: str = ""
    image_base64: str = ""
    model_name: str = "doubao"


# ---- Vision only ----

@router.post("/vision")
async def vision_only(req: VisionRequest):
    """识别图片 + 自动创建对话（带学科标签）"""
    t0 = time.time()
    router_instance = ModelRouter()
    available = [p["name"] for p in router_instance.list_vision_providers()]
    if req.model_name not in available:
        await logs.add_log("vision", req.model_name, req.mode, "error", 0, "model check", "", f"unknown model: {req.model_name}")
        raise HTTPException(400, f"Model '{req.model_name}' not available. Available: {available}")

    db_conn = await db.get_db()
    try:
        image_hash = compute_image_hash(req.image_base64)
        existing_conversation = await conv.find_conversation_by_image(
            image_hash=image_hash,
            mode=req.mode,
            subject=req.subject,
        )
        from_cache = False
        if not req.force_refresh:
            if existing_conversation and existing_conversation.get("vision_result"):
                if req.subject and not existing_conversation.get("subject"):
                    await conv.update_conversation_subject(existing_conversation["id"], req.subject)
                if req.image_base64 and not existing_conversation.get("image_base64"):
                    await conv.update_conversation_image(existing_conversation["id"], req.image_base64)
                vision_result = existing_conversation["vision_result"]
                from_cache = True
                dur = int((time.time() - t0) * 1000)
                await logs.add_log("vision", req.model_name, req.mode, "ok", dur,
                    f"hash={image_hash[:12]} reused_conversation={existing_conversation['id']}",
                    vision_result[:200])
                return {
                    "vision_result": vision_result,
                    "from_cache": True,
                    "conversation_id": existing_conversation["id"],
                    "deduped": True,
                    "image_base64": existing_conversation.get("image_base64") or req.image_base64,
                }
            cached = await db.get_cached_vision(db_conn, image_hash, req.model_name)
            if cached:
                vision_result = cached
                from_cache = True
        if not from_cache:
            provider = router_instance.get_vision_provider(req.model_name)
            vision_result = await provider.analyze_image(req.image_base64)
            await db.set_cached_vision(db_conn, image_hash, req.model_name, vision_result)

        if existing_conversation:
            conversation_id = existing_conversation["id"]
            await conv.update_conversation_vision(conversation_id, vision_result)
            if req.image_base64 and existing_conversation.get("image_base64") != req.image_base64:
                await conv.update_conversation_image(conversation_id, req.image_base64)
            if req.subject and existing_conversation.get("subject") != req.subject:
                await conv.update_conversation_subject(conversation_id, req.subject)
        else:
            conversation_id = await conv.create_conversation(
                image_hash=image_hash,
                image_base64=req.image_base64,
                vision_result=vision_result,
                mode=req.mode,
                subject=req.subject,
            )

        dur = int((time.time() - t0) * 1000)
        await logs.add_log("vision", req.model_name, req.mode, "ok", dur,
            f"hash={image_hash[:12]} cache={from_cache} force={req.force_refresh}",
            vision_result[:200])

        return {
            "vision_result": vision_result,
            "from_cache": from_cache,
            "conversation_id": conversation_id,
            "deduped": bool(existing_conversation),
            "image_base64": req.image_base64,
        }
    except Exception as e:
        dur = int((time.time() - t0) * 1000)
        await logs.add_log("vision", req.model_name, req.mode, "error", dur, "", "", str(e)[:500])
        logger.exception("Vision error")
        raise HTTPException(500, f"Vision failed: {e}")
    finally:
        await db_conn.close()


# ---- Subject-aware context builder ----

def _build_subject_context(mode_config: dict, subject: str, mode: str) -> str:
    """构建带学科知识的系统提示词"""
    prompt = mode_config["prompt"]
    if not subject:
        return prompt
    return f"{prompt}\n\n当前学科领域：{subject}。请结合该学科的知识体系来回答问题。"


# ---- Multi-turn Chat ----

@router.post("/chat")
async def chat(req: ChatRequest):
    t0 = time.time()
    router_instance = ModelRouter()

    # 情况1：已有对话
    if req.conversation_id:
        conversation = await conv.get_conversation(req.conversation_id)
        if not conversation:
            raise HTTPException(404, f"Conversation '{req.conversation_id}' not found")

        mode_config = ANALYSIS_MODES.get(conversation["mode"], ANALYSIS_MODES["general"])
        subject = conversation.get("subject", "") or req.subject

        # 缓存友好结构：[system] [vision_context] [last_A?] [last_Q?] [new_Q]
        system_prompt = _build_subject_context(mode_config, subject, conversation["mode"])

        # 学科知识摘要（如果存在）
        if subject:
            note = await conv.get_subject_note(subject, conversation["mode"])
            if note and note.get("summary"):
                system_prompt += f"\n\n该学科之前讨论过的要点：{note['summary']}"

        messages = [{"role": "system", "content": system_prompt}]

        if conversation["vision_result"]:
            messages.append({
                "role": "user",
                "content": f"以下是一道题目的内容，请根据内容回答后续问题：\n\n{conversation['vision_result']}"
            })

        # 只带最近一轮
        for msg in reversed(conversation["messages"]):
            if msg["role"] == "assistant":
                messages.append({"role": "assistant", "content": msg["content"]})
                break
        for msg in reversed(conversation["messages"]):
            if msg["role"] == "user":
                messages.append({"role": "user", "content": msg["content"]})
                break

        messages.append({"role": "user", "content": req.user_question})

        await conv.append_message(req.conversation_id, "user", req.user_question)

        try:
            provider = router_instance.get_language_provider()
            result = await provider.chat(messages)
            await conv.append_message(req.conversation_id, "assistant", result)

            # 更新学科知识摘要
            if subject:
                await _update_subject_summary(subject, conversation["mode"], result)

            dur = int((time.time() - t0) * 1000)
            await logs.add_log("chat", "deepseek", conversation["mode"], "ok", dur,
                f"conv={req.conversation_id[:12]} subject={subject} q={req.user_question[:80]}",
                result[:200])
            return {"analysis_result": result, "conversation_id": req.conversation_id, "subject": subject}
        except Exception as e:
            dur = int((time.time() - t0) * 1000)
            await logs.add_log("chat", "deepseek", conversation.get("mode",""), "error", dur,
                f"conv={req.conversation_id[:12]} q={req.user_question[:80]}", "", str(e)[:500])
            logger.exception("Chat error")
            raise HTTPException(500, f"Chat failed: {e}")

    # 情况2：新对话 + 有图片
    if req.image_base64:
        vis_resp = await vision_only(VisionRequest(
            image_base64=req.image_base64,
            model_name=req.model_name,
            mode=req.mode,
            subject=req.subject,
        ))
        return await chat(ChatRequest(
            user_question=req.user_question,
            conversation_id=vis_resp["conversation_id"],
            mode=req.mode,
            subject=req.subject,
        ))

    # 情况3：纯文字
    mode_config = ANALYSIS_MODES.get(req.mode, ANALYSIS_MODES["general"])
    system_prompt = _build_subject_context(mode_config, req.subject, req.mode)
    try:
        provider = router_instance.get_language_provider()
        result = await provider.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.user_question},
        ])
        dur = int((time.time() - t0) * 1000)
        await logs.add_log("chat", "deepseek", req.mode, "ok", dur,
            f"text-only subject={req.subject} q={req.user_question[:80]}",
            result[:200])
        return {"analysis_result": result, "conversation_id": "", "subject": req.subject}
    except Exception as e:
        dur = int((time.time() - t0) * 1000)
        await logs.add_log("chat", "deepseek", req.mode, "error", dur,
            f"text-only q={req.user_question[:80]}", "", str(e)[:500])
        logger.exception("Chat error")
        raise HTTPException(500, f"Chat failed: {e}")


async def _update_subject_summary(subject: str, mode: str, latest_reply: str):
    """用最新回复更新学科知识摘要（取前 200 字作为要点）"""
    existing = await conv.get_subject_note(subject, mode)
    old = existing["summary"] if existing else ""
    # 提取最新回复的关键句（前 200 字）
    new_points = latest_reply[:200].strip()
    if old:
        merged = f"{old} | {new_points}" if new_points not in old else old
    else:
        merged = new_points
    # 限制总长度
    if len(merged) > 2000:
        merged = merged[-2000:]
    await conv.update_subject_note(subject, mode, merged)


# ---- Conversations ----

@router.get("/conversations")
async def list_conversations(limit: int = 50):
    conversations = await conv.list_conversations(limit)
    # 按 subject 分组
    subjects = {}
    for c in conversations:
        s = c.get("subject", "") or "未分类"
        if s not in subjects:
            subjects[s] = []
        subjects[s].append(c)

    return {
        "conversations": conversations,
        "by_subject": {k: subjects[k] for k in sorted(subjects.keys())},
    }


@router.get("/conversation/{conv_id}")
async def get_conversation(conv_id: str):
    conversation = await conv.get_conversation(conv_id)
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    return conversation


@router.get("/subjects")
async def list_subjects(mode: str = "exam"):
    subjects = await conv.list_subjects(mode)
    return {"subjects": subjects}


@router.post("/conversation/{conv_id}/subject")
async def set_conversation_subject(conv_id: str, subject: str = ""):
    await conv.update_conversation_subject(conv_id, subject)
    return {"ok": True}


# ---- Reconstruct ----

RECONSTRUCT_PROMPT = """你是一个题目还原助手。请根据图片识别结果，忠实地还原原始题目。

要求：
1. 用完整的文字重新表述题目，包括已知条件、待求问题、选项等
2. 如果有图形，分两层描述：
   - 图层1「几何结构」：坐标系、圆心、半径、各点坐标或位置
   - 图层2「标注关系」：角度、垂线、切线、弧长等几何关系
3. 保留所有公式，用 $$ 或 $ 包裹；不要输出未包裹的 LaTeX 命令
4. 如果有选项图（函数图像），逐项描述每条曲线的形状、峰值位置、零点位置
5. 不添加任何解答、提示或分析，只输出题目原文
6. 如果识别结果包含几何图、函数图像、坐标系、圆、切线、垂线、曲线选项等图形信息，请在正文最后追加一个 fenced code block，语言名必须是 deepimage-graph，内容是 JSON。这个 JSON 是你给前端的绘图指令，必须尽量贴合原图，不要让前端猜图。
重要：JSON 中的点名必须严格使用原题中的点名，禁止使用示例中的点名替代原图的点名。
如果是单位圆坐标系题：圆心 O 固定为 {"x":0,"y":0}，x 轴正向上的圆点坐标 {"x":1,"y":0}，圆上一点对应圆心角可用 {"x":0.7,"y":0.7}，垂足与原点 x 坐标相同 y=0，切点纵坐标为 tan(x)。
```deepimage-graph
{
  "type": "geometry",
  "title": "图例",
  "elements": [
    {"kind": "circle", "label": "O", "cx": 0, "cy": 0, "r": 1},
    {"kind": "point", "label": "O", "x": 0, "y": 0},
    {"kind": "point", "label": "C1", "x": 1, "y": 0},
    {"kind": "point", "label": "B1", "x": 0.7, "y": 0.7},
    {"kind": "point", "label": "D1", "x": 0.7, "y": 0},
    {"kind": "line", "label": "OC1", "from": "O", "to": "C1"},
    {"kind": "line", "label": "OB1", "from": "O", "to": "B1"},
    {"kind": "line", "label": "B1D1", "from": "B1", "to": "D1", "style": "dashed"},
    {"kind": "right_angle", "at": "D1"},
    {"kind": "angle", "label": "x", "at": "O", "from": "C1", "to": "B1"}
  ]
}
```
7. 几何元素只输出原图存在的线段、圆、角、垂线和标注；不要补不存在的切线、辅助线或额外坐标轴。
8. 曲线选项要分别输出 A/B/C/D，每个选项写清 shape、峰值高度 peak_y、零点 zeros。x 坐标统一归一化到 0 到 1，表示题目横轴区间。
9. 图形 JSON 只用于前端画图，不要把它当作题目内容解释。"""


class ReconstructRequest(BaseModel):
    vision_result: str
    conversation_id: str = ""
    mode: str = "exam"


@router.post("/reconstruct")
async def reconstruct_problem(req: ReconstructRequest):
    """根据豆包识别结果还原题目原文（缓存友好：system prompt 固定不变）"""
    router_instance = ModelRouter()
    try:
        provider = router_instance.get_language_provider()
        result = await provider.chat([
            {"role": "system", "content": RECONSTRUCT_PROMPT},
            {"role": "user", "content": f"请根据以下识别结果还原原始题目：\n\n{req.vision_result}"},
        ])
        # 解析并渲染图形
        graph_b64 = ""
        graph_json = parse_graph_json(result)
        if graph_json:
            try:
                graph_b64 = render_graph(graph_json)
            except Exception as e:
                logger.warning("Graph render failed: %s", e)

        # 保存到对话
        if req.conversation_id:
            await conv.save_reconstructed(req.conversation_id, result)
        return {"problem": result, "graph_base64": graph_b64}
    except Exception as e:
        logger.exception("Reconstruct error")
        raise HTTPException(500, f"Reconstruct failed: {e}")


# ---- Logs ----

@router.get("/logs")
async def get_logs(limit: int = 50):
    all_logs = await logs.list_logs(limit)
    # 统计
    ok_count = sum(1 for l in all_logs if l["status"] == "ok")
    err_count = sum(1 for l in all_logs if l["status"] == "error")
    return {"logs": all_logs, "total": len(all_logs), "ok": ok_count, "error": err_count}


# ---- PDF Export ----

def _build_export_html(conversation: dict, subject: str) -> str:
    msgs = conversation.get("messages", []) or []
    vision = conversation.get("vision_result", "") or ""
    reconstructed = conversation.get("reconstructed", "") or ""
    created = (conversation.get("created_at", "") or "")[:19]

    chat_html = ""
    for m in msgs:
        role = "我" if m["role"] == "user" else "DeepSeek"
        chat_html += f'<div class="msg {m["role"]}"><strong>{role}：</strong>{m["content"]}</div>\n'

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>题目导出</title>
<style>body{{font-family:"PingFang SC","Microsoft YaHei",sans-serif;max-width:800px;margin:0 auto;padding:20px;line-height:1.8;color:#333}}
h1{{color:#ef3f52}}h2{{color:#555;border-bottom:2px solid #ef3f52;padding-bottom:6px}}
.block{{background:#fafafa;border:1px solid #ddd;border-radius:8px;padding:16px;margin:12px 0;white-space:pre-wrap}}
.msg{{margin:8px 0;padding:8px 12px;border-radius:6px}}
.msg.user{{background:#eef5ff}}.msg.assistant{{background:#fff5f5}}
.footer{{margin-top:30px;color:#999;font-size:12px;text-align:center}}
</style></head><body>
<h1>考研题目记录</h1>
<p><strong>学科：</strong>{subject} &nbsp;|&nbsp; <strong>时间：</strong>{created}</p>
<h2>豆包识别结果</h2>
<div class="block">{vision}</div>
<h2>题目还原</h2>
<div class="block">{reconstructed or '（未还原）'}</div>
<h2>对话记录</h2>
<div>{chat_html or '（无对话）'}</div>
<div class="footer">由 Deep-Image 生成</div>
</body></html>"""


@router.get("/export/{conv_id}")
async def export_pdf(conv_id: str):
    conversation = await conv.get_conversation(conv_id)
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    try:
        from weasyprint import HTML
        html = _build_export_html(conversation, conversation.get("subject", ""))
        pdf = HTML(string=html).write_pdf()
        return Response(content=pdf, media_type="application/pdf",
                       headers={"Content-Disposition": f"attachment; filename=deep-image-{conv_id}.pdf"})
    except Exception as e:
        logger.exception("PDF export error")
        raise HTTPException(500, f"PDF export failed: {e}")


# ---- Models & Modes ----

@router.get("/models")
async def list_models():
    router = ModelRouter()
    return {"models": router.list_vision_providers()}


@router.get("/modes")
async def list_modes():
    return {
        "modes": [
            {"id": k, "name": v["name"]}
            for k, v in ANALYSIS_MODES.items()
        ]
    }
