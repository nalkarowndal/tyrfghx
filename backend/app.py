from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from model_catalog import MODEL_ROOT as DEFAULT_MODEL_ROOT, ModelRecord, scan_models
from model_compatibility import CompatibilityReport, check_pair
from typing import Annotated
from fastapi import Query
from pathlib import Path
import re
import secrets
from starlette.responses import JSONResponse

MODEL_ROOT = DEFAULT_MODEL_ROOT

def health():
    return {"ok": True}

def status():
    return {
        "app": "aiimage", "version": "0.1.0", "mode": "foundation",
        "engines": [
            {"name": "Local PyTorch/Diffusers", "status": "unavailable", "note": "이 API 패키지에는 GPU 추론 런타임이 포함되지 않습니다."},
            {"name": "ComfyUI (optional)", "status": "unavailable", "note": "연동되지 않음"},
        ],
    }

def create_app(model_root: Path | None = None, token: str | None = None) -> FastAPI:
    """Packaged mode is authenticated and native-only; None preserves explicit dev use."""
    if token is not None and re.fullmatch(r"[0-9a-f]{64}", token) is None:
        raise ValueError("Invalid backend session token")
    packaged = token is not None
    instance = FastAPI(title="aiimage local API", version="0.1.0",
                       docs_url=None if packaged else "/docs",
                       redoc_url=None if packaged else "/redoc",
                       openapi_url=None if packaged else "/openapi.json")
    if packaged:
        @instance.middleware("http")
        async def authorize(request, call_next):
            # Ignore proxy headers. Only the native parent may call this API.
            host = request.headers.get("host", "")
            if (not request.client or request.client.host != "127.0.0.1"
                    or re.fullmatch(r"127\.0\.0\.1(?::[0-9]{1,5})?", host) is None
                    or "origin" in request.headers):
                return JSONResponse({"detail": "Forbidden"}, status_code=403)
            value = request.headers.get("authorization", "")
            if not secrets.compare_digest(value.encode(), f"Bearer {token}".encode()):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            return await call_next(request)
    else:
        instance.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"], allow_methods=["GET"], allow_headers=["*"])

    instance.get("/api/health")(health)
    instance.get("/api/status")(status)

    @instance.get("/api/models", response_model=list[ModelRecord])
    def get_models():
        return scan_models(model_root if model_root is not None else MODEL_ROOT)

    @instance.get("/api/models/compatibility", response_model=CompatibilityReport)
    def get_compatibility(
        checkpoint_id: Annotated[str, Query(min_length=1, max_length=256)],
        lora_id: Annotated[str, Query(min_length=1, max_length=256)],
    ):
        return check_pair(model_root if model_root is not None else MODEL_ROOT, checkpoint_id, lora_id)
    return instance


app = create_app()  # Explicit browser development only; bundled_server uses a token.
