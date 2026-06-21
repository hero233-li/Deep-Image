from app.engine.base import VisionProvider, LanguageProvider
from app.engine.providers.doubao import DoubaoVisionProvider
from app.engine.providers.kimi import KimiVisionProvider
from app.engine.providers.deepseek_vision import DeepSeekVisionProvider
from app.engine.providers.deepseek_language import DeepSeekLanguageProvider
from app.config import VISION_PROVIDERS, LANGUAGE_PROVIDER


class ModelRouter:
    def __init__(self):
        self._vision_registry: dict[str, type[VisionProvider]] = {
            "doubao": DoubaoVisionProvider,
            "kimi": KimiVisionProvider,
            "deepseek": DeepSeekVisionProvider,
        }
        self._language_provider = DeepSeekLanguageProvider(
            api_key=LANGUAGE_PROVIDER["api_key"],
            base_url=LANGUAGE_PROVIDER["base_url"],
            model=LANGUAGE_PROVIDER["model"],
        )

    def get_vision_provider(self, name: str) -> VisionProvider:
        provider_cls = self._vision_registry.get(name)
        if not provider_cls:
            available = list(self._vision_registry.keys())
            raise ValueError(f"Unknown vision model '{name}'. Available: {available}")

        cfg = VISION_PROVIDERS.get(name, {})
        return provider_cls(
            api_key=cfg.get("api_key", ""),
            base_url=cfg.get("base_url", ""),
            model=cfg.get("model", ""),
        )

    def get_language_provider(self) -> LanguageProvider:
        return self._language_provider

    def list_vision_providers(self) -> list[dict]:
        return [
            {"name": name, "model": VISION_PROVIDERS[name]["model"]}
            for name in self._vision_registry
        ]
