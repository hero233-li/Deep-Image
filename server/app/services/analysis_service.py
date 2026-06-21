import hashlib
from app.engine.router import ModelRouter
from app.config import ANALYSIS_MODES
from app.models import database as db
from app.services.image_service import compute_image_hash
from app.utils.logger import logger


def _build_cache_key(vision_result: str, mode: str, user_question: str) -> str:
    raw = f"{vision_result}|||{mode}|||{user_question}"
    return hashlib.sha256(raw.encode()).hexdigest()


class AnalysisService:
    def __init__(self, router: ModelRouter):
        self.router = router

    async def analyze(
        self,
        image_base64: str,
        model_name: str,
        mode: str = "code",
        user_question: str = "",
    ) -> dict:
        """分析图片，返回 {vision_result, analysis_result, from_cache, vision_from_cache, analysis_from_cache}"""
        db_conn = await db.get_db()
        try:
            image_hash = compute_image_hash(image_base64)

            # Step 1: 查图片缓存
            vision_from_cache = False
            vision_result = await db.get_cached_vision(db_conn, image_hash, model_name)
            if vision_result:
                logger.info("Image cache HIT for hash=%s model=%s", image_hash[:16], model_name)
                vision_from_cache = True
            else:
                logger.info("Image cache MISS, calling vision model '%s'...", model_name)
                vision_provider = self.router.get_vision_provider(model_name)
                vision_result = await vision_provider.analyze_image(image_base64)
                await db.set_cached_vision(db_conn, image_hash, model_name, vision_result)

            # Step 2: 查分析缓存（vision_result + mode + question 组合）
            analysis_from_cache = False
            cache_key = _build_cache_key(vision_result, mode, user_question)
            analysis_result = await db.get_cached_analysis(db_conn, cache_key)
            if analysis_result:
                logger.info("Analysis cache HIT for key=%s", cache_key[:16])
                analysis_from_cache = True
            else:
                logger.info("Analysis cache MISS, calling language model (mode=%s)...", mode)
                mode_config = ANALYSIS_MODES.get(mode, ANALYSIS_MODES["code"])
                system_prompt = mode_config["prompt"]
                user_content = f"图片识别结果如下：\n\n{vision_result}"
                if user_question:
                    user_content += f"\n\n用户提问：{user_question}"

                language_provider = self.router.get_language_provider()
                analysis_result = await language_provider.chat([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ])
                await db.set_cached_analysis(db_conn, cache_key, analysis_result)

            return {
                "vision_result": vision_result,
                "analysis_result": analysis_result,
                "vision_from_cache": vision_from_cache,
                "analysis_from_cache": analysis_from_cache,
            }
        finally:
            await db_conn.close()

    async def analyze_and_save(
        self,
        image_base64: str,
        model_name: str,
        filename: str,
        image_path: str,
        mode: str = "code",
        user_question: str = "",
    ) -> str:
        db_conn = await db.get_db()
        record_id = None
        try:
            result = await self.analyze(image_base64, model_name, mode, user_question)
            record_id = await db.create_record(
                db_conn, filename, image_path, model_name,
                mode=mode, user_question=user_question,
                from_cache=result["analysis_from_cache"],
            )
            await db.update_record(
                db_conn, record_id, result["vision_result"], result["analysis_result"],
                from_cache=result["analysis_from_cache"],
            )
            return record_id
        except Exception as e:
            logger.exception("Analysis failed")
            if record_id:
                await db.update_record(db_conn, record_id, "", str(e), "failed")
            raise
        finally:
            await db_conn.close()
