import base64
import hashlib
import uuid
from io import BytesIO
from pathlib import Path
from PIL import Image
from app.config import UPLOAD_DIR, MAX_IMAGE_SIZE
from app.utils.logger import logger


def save_upload(file_data: bytes, original_filename: str) -> tuple[str, str]:
    """保存上传的图片，返回 (file_path, base64_string)"""
    ext = Path(original_filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        ext = ".png"

    file_id = uuid.uuid4().hex
    filename = f"{file_id}{ext}"
    file_path = UPLOAD_DIR / filename
    file_path.write_bytes(file_data)
    logger.info("Saved image: %s (%d bytes)", filename, len(file_data))

    img = Image.open(BytesIO(file_data))
    img = _preprocess(img)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")

    return str(file_path), b64


def _preprocess(img: Image.Image, max_side: int = 2048) -> Image.Image:
    """限制图片尺寸，避免发送过大的 base64"""
    w, h = img.size
    if w <= max_side and h <= max_side:
        return img
    ratio = max_side / max(w, h)
    new_size = (int(w * ratio), int(h * ratio))
    return img.resize(new_size, Image.LANCZOS)


def compute_image_hash(image_b64: str) -> str:
    """对 base64 图片内容做 SHA256，用于缓存匹配"""
    return hashlib.sha256(image_b64.encode()).hexdigest()


def read_file_bytes(file_data: bytes) -> str:
    """读取原始字节转为 base64"""
    img = Image.open(BytesIO(file_data))
    img = _preprocess(img)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def image_to_base64(file_path: str, max_side: int = 2048) -> str:
    """读取已有图片并转为 base64"""
    img = Image.open(file_path)
    img = _preprocess(img, max_side)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")
