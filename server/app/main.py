from contextlib import asynccontextmanager
from pathlib import Path
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api import upload, analysis, models_info, update, history
from app.models.database import init_db
from app.models.conversation import init_conversations_table
from app.models.logs import init_logs_table, add_log
from app.utils.logger import logger

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    await init_conversations_table()
    await init_logs_table()
    logger.info("Server ready.")
    yield


app = FastAPI(title="Deep-Image", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_log_middleware(request, call_next):
    start = time.time()
    status = "ok"
    status_code = 500
    error_detail = ""
    try:
        response = await call_next(request)
        status_code = response.status_code
        if status_code >= 400:
            status = "error"
        return response
    except Exception as exc:
        status = "error"
        error_detail = str(exc)[:500]
        raise
    finally:
        duration_ms = int((time.time() - start) * 1000)
        try:
            query = str(request.url.query)
            summary = f"{request.method} {request.url.path}"
            if query:
                summary += f"?{query[:180]}"
            await add_log(
                endpoint="http",
                model_name=request.url.path[:120],
                status=status,
                duration_ms=duration_ms,
                request_summary=summary,
                response_summary=f"status={status_code}",
                error_detail=error_detail,
            )
        except Exception:
            logger.exception("Failed to write request log")

app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])
app.include_router(models_info.router, prefix="/api", tags=["models"])
app.include_router(update.router, prefix="/api", tags=["update"])
app.include_router(history.router, prefix="/api", tags=["history"])


STATIC_DIR.mkdir(exist_ok=True)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/css", StaticFiles(directory=str(STATIC_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(STATIC_DIR / "js")), name="js")
