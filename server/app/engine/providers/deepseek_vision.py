import httpx
from app.engine.base import VisionProvider
from app.utils.logger import logger


class DeepSeekVisionProvider(VisionProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def analyze_image(self, image_base64: str, prompt: str | None = None) -> str:
        if prompt is None:
            prompt = "请识别并输出图片中的所有文字内容，逐行原样输出，不要添加任何解释或描述。"
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
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            result = data["choices"][0]["message"]["content"]
            logger.info("DeepSeek vision result: %s chars", len(result))
            return result
