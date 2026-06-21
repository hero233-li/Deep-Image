import asyncio
import httpx
from app.engine.base import VisionProvider
from app.utils.logger import logger

RETRIES = 2
TIMEOUT = 120


class DoubaoVisionProvider(VisionProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def analyze_image(self, image_base64: str, prompt: str | None = None) -> str:
        if prompt is None:
            prompt = "请完整描述这张图片中的所有内容：\n1. 识别所有文字，逐行原样输出\n2. 如果有图像/图形/曲线/图表，描述其形状、走势、关键点位置、坐标等视觉特征\n3. 如果有几何图形，描述点线面之间的位置关系\n直接输出内容，不要加任何解释。"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        last_error = None
        for attempt in range(RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    result = data["choices"][0]["message"]["content"]
                    logger.info("Doubao vision result: %s chars (attempt %d)", len(result), attempt + 1)
                    return result
            except Exception as e:
                last_error = e
                if attempt < RETRIES:
                    wait = (attempt + 1) * 3
                    logger.warning("Doubao attempt %d failed: %s, retrying in %ds...", attempt + 1, e, wait)
                    await asyncio.sleep(wait)

        raise last_error
