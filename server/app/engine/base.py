from abc import ABC, abstractmethod


class VisionProvider(ABC):
    """视觉模型统一接口"""

    @abstractmethod
    async def analyze_image(self, image_base64: str, prompt: str | None = None) -> str:
        """识别图片内容，返回文字描述"""
        ...


class LanguageProvider(ABC):
    """语言模型统一接口"""

    @abstractmethod
    async def chat(self, messages: list[dict]) -> str:
        """多轮对话"""
        ...
