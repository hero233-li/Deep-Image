import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# 优先加载 .env 文件（如果存在）
env_file = BASE_DIR / ".env"
if env_file.exists():
    load_dotenv(env_file)

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DATABASE_PATH = BASE_DIR / "data.db"


def _get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


VISION_PROVIDERS = {
    "doubao": {
        "api_key": _get_env("DOUBAO_API_KEY"),
        "base_url": _get_env("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        "model": _get_env("DOUBAO_MODEL", "doubao-vision-pro-32k"),
    },
    "kimi": {
        "api_key": _get_env("KIMI_API_KEY"),
        "base_url": _get_env("KIMI_BASE_URL", "https://api.moonshot.cn/v1"),
        "model": _get_env("KIMI_MODEL", "moonshot-v1-32k-vision-preview"),
    },
    "deepseek": {
        "api_key": _get_env("DEEPSEEK_API_KEY"),
        "base_url": _get_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        "model": _get_env("DEEPSEEK_VISION_MODEL", "deepseek-vl2"),
    },
}

LANGUAGE_PROVIDER = {
    "api_key": _get_env("DEEPSEEK_API_KEY"),
    "base_url": _get_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    "model": _get_env("DEEPSEEK_MODEL", "deepseek-chat"),
}

SERVER_HOST = _get_env("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(_get_env("SERVER_PORT", "8000"))
APP_VERSION = _get_env("APP_VERSION", "0.1.0")
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# 分析模式
ANALYSIS_MODES = {
    "exam": {
        "name": "考研助手",
        "prompt": """你是一位资深的考研辅导老师，擅长解析各科目的题目。
你收到的"图片识别结果"包含两部分：文字内容和图像视觉描述（如函数曲线形状、几何图形结构、走势趋势等）。
请结合文字和视觉信息，帮助学生完成以下分析：

1. **题目重构**：用简洁的文字还原完整题目（包括选项和图形信息）
2. **题目类型识别**：判断这是什么科目、什么题型的题目
3. **知识点梳理**：列出本题考察的核心知识点
4. **解题思路**：给出清晰的解题步骤和思考过程
5. **答案**：给出最终结果
6. **要点总结**：总结此类题目的解题技巧和易错点

请用 Markdown 格式回复，数学公式用 $$ 或 $ 包裹。""",
    },
    "code": {
        "name": "代码分析",
        "prompt": """你是一个专业的技术助手，擅长分析图片中的代码错误和技术问题。
请根据图片识别结果，进行以下分析：

1. **问题定位**：如果图片包含错误信息，请指出具体错误类型和位置
2. **原因分析**：解释为什么会出现这个问题
3. **解决方案**：给出具体、可操作的解决步骤
4. **预防建议**：如何避免类似问题再次发生

请用 Markdown 格式回复，结构清晰。""",
    },
    "general": {
        "name": "通用问答",
        "prompt": """你是一个智能助手，用户上传了一张图片并可能附带了问题。
请根据图片识别结果，结合用户的问题（如果有），给出有帮助的回答。

如果用户有明确的问题，请针对性回答。
如果用户只是上传了图片，请描述图片内容并询问用户想了解什么。

请用 Markdown 格式回复。""",
    },
}
