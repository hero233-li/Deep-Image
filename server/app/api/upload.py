from fastapi import APIRouter, UploadFile, File, HTTPException
from app.config import MAX_IMAGE_SIZE
from app.services.image_service import save_upload

router = APIRouter()


@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Only image files are accepted")

    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(400, f"Image too large (max {MAX_IMAGE_SIZE // 1024 // 1024}MB)")

    file_path, image_b64 = save_upload(content, file.filename or "image.png")

    return {
        "image_base64": image_b64,
        "filename": file.filename,
        "image_path": file_path,
    }
