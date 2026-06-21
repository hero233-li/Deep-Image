from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from app.config import APP_VERSION, BASE_DIR

router = APIRouter()

APK_DIR = BASE_DIR / "apk"


@router.get("/version")
async def get_version():
    apk_available = False
    apk_path = APK_DIR / "latest.apk"
    if apk_path.exists():
        apk_available = True

    return {
        "version": APP_VERSION,
        "apk_available": apk_available,
        "apk_url": "/api/apk/latest" if apk_available else None,
    }


@router.get("/apk/latest")
async def download_apk():
    apk_path = APK_DIR / "latest.apk"
    if not apk_path.exists():
        raise HTTPException(404, "No APK available")
    return FileResponse(apk_path, media_type="application/vnd.android.package-archive", filename="deep-image.apk")
