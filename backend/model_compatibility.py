"""Conservative metadata-family assessment; never promises inference compatibility."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from model_catalog import ModelRecord, scan_models


class CompatibilityReport(BaseModel):
    status: Literal["possible_match", "family_mismatch", "unknown", "blocked", "not_found", "invalid_selection"]
    checkpoint_id: str
    lora_id: str
    summary: str


def evaluate_pair(records: list[ModelRecord], checkpoint_id: str, lora_id: str) -> CompatibilityReport:
    by_id = {item.id: item for item in records}
    checkpoint, lora = by_id.get(checkpoint_id), by_id.get(lora_id)
    status: CompatibilityReport.model_fields["status"].annotation
    if not checkpoint or not lora:
        status, summary = "not_found", "선택된 모델 파일이 현재 목록에 없습니다."
    elif checkpoint.category != "checkpoint" or lora.category != "lora":
        status, summary = "invalid_selection", "체크포인트와 LoRA를 각각 선택해야 합니다."
    elif checkpoint.validation != "metadata_only" or lora.validation != "metadata_only":
        status, summary = "blocked", "헤더 오류 또는 안전하지 않은 형식의 파일이 포함되어 있습니다."
    elif not checkpoint.family or not lora.family:
        status, summary = "unknown", "계열 정보가 충분하지 않아 사전 일치 여부를 판단할 수 없습니다."
    elif checkpoint.family != lora.family:
        status, summary = "family_mismatch", "모델 계열이 서로 다릅니다. 로딩 전 추가 확인이 필요합니다."
    else:
        status, summary = "possible_match", "메타데이터상 모델 계열이 같습니다. 실제 호환성 및 GPU 실행은 미검증입니다."
    return CompatibilityReport(status=status, checkpoint_id=checkpoint_id, lora_id=lora_id, summary=summary)


def check_pair(root: Path, checkpoint_id: str, lora_id: str) -> CompatibilityReport:
    return evaluate_pair(scan_models(root), checkpoint_id, lora_id)
