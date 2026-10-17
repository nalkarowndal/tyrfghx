from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from model_catalog import MODEL_ROOT as DEFAULT_MODEL_ROOT, ModelRecord, scan_models
from model_compatibility import CompatibilityReport, check_pair
from typing import Annotated
from fastapi import Query

MODEL_ROOT = DEFAULT_MODEL_ROOT

app = FastAPI(title="aiimage local API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"], allow_methods=["GET"], allow_headers=["*"])

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/status")
def status():
    return {
        "app": "aiimage", "version": "0.1.0", "mode": "foundation",
        "engines": [
            {"name": "Local PyTorch/Diffusers", "status": "unavailable", "note": "M3에서 GPU 추론 구현 예정"},
            {"name": "ComfyUI (optional)", "status": "unavailable", "note": "연동되지 않음"},
        ],
    }

@app.get("/api/models", response_model=list[ModelRecord])
def get_models():
    return scan_models(MODEL_ROOT)

@app.get("/api/models/compatibility", response_model=CompatibilityReport)
def get_compatibility(
    checkpoint_id: Annotated[str, Query(min_length=1, max_length=256)],
    lora_id: Annotated[str, Query(min_length=1, max_length=256)],
):
    return check_pair(MODEL_ROOT, checkpoint_id, lora_id)
