"""M2: deterministic, non-authorizing orphan-review preview.

Takes already-captured catalog metadata and an in-memory manifest snapshot.
Does NOT read filesystem paths, hash real model files, register or delete
models, set Tauri permissions, invoke package installers or access GPUs.

Any 'review_required' result means an independent, explicitly approved
source/identity/provenance check is STILL REQUIRED. It never authorizes
a registry write, model execution or deletion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from model_catalog import MODEL_FOLDERS, ModelRecord
from model_integrity import IntegrityEntry
from model_metadata import valid_id

ReviewStatus = Literal[
    "review_required",
    "invalid_candidate",
    "invalid_manifest",
    "not_an_orphan",
    "invalid_observation",
]


@dataclass(frozen=True)
class OrphanReview:
    status: ReviewStatus
    reason: str
    model_id: str | None
    snapshot_sha256: str | None
    can_register: bool = False
    can_delete: bool = False
    can_execute: bool = False
    requires_human_review: bool = True
    files_opened: bool = False
    files_modified: bool = False
    trusted_provenance_verified: bool = False


def preview_orphan_review(
    record: ModelRecord | None,
    *,
    manifest_ok: bool,
    existing_entry: IntegrityEntry | None,
) -> OrphanReview:
    """Preview next review step using only untrusted, cached observation data.

    The caller MUST separately verify ownership, provenance, opened-handle
    identity, trust anchor and live SHA256 before any future registration.
    """
    if manifest_ok is not True or (
        existing_entry is not None and not isinstance(existing_entry, IntegrityEntry)
    ):
        return OrphanReview("invalid_manifest", "manifest_requires_manual_review", None, None)
    if record is None or not isinstance(record, ModelRecord):
        return OrphanReview("invalid_observation", "catalog_observation_missing", None, None)
    if not valid_id(record.id):
        return OrphanReview("invalid_observation", "model_id_invalid", None, None)
    category_folder, filename = record.id.split("/")
    if (record.name != filename
            or record.category != MODEL_FOLDERS.get(category_folder)):
        return OrphanReview("invalid_observation", "catalog_identity_conflict", None, None)
    if record.file_format != "safetensors" or record.validation != "metadata_only":
        return OrphanReview("invalid_candidate", "unsupported_or_invalid_model_metadata", record.id, None)
    if record.size_bytes <= 0:
        return OrphanReview("invalid_candidate", "size_not_positive", record.id, None)
    if existing_entry is not None:
        return OrphanReview(
            "not_an_orphan", "manifest_entry_already_exists", record.id,
            existing_entry.sha256,
        )
    if record.integrity_state != "not_recorded" or record.recorded_sha256 is not None:
        return OrphanReview(
            "invalid_observation", "catalog_manifest_conflict", record.id, None,
        )
    # The metadata-only catalog record does not prove source provenance,
    # real-time file identity or trusted content. Do not label it as verified.
    return OrphanReview(
        "review_required", "manual_source_identity_and_hash_review_required",
        record.id, None,
    )
