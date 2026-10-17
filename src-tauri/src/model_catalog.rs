//! Read-only local model catalog for the Tauri desktop app.
//! Shares the exact model-root and integrity registry created by model_import.
//! This command never accepts paths from the webview and never deserializes weights.

use serde::Serialize;
use serde_json::Value;
use std::fs::{self, File};
use std::io::Read;
use std::path::Path;

const MAX_HEADER: u64 = 1_048_576;
const MAX_REGISTRY: u64 = 1_048_576;
const MAX_ENTRIES: usize = 3_000;

#[derive(Clone, Serialize)]
pub struct ModelRecord {
    pub(crate) id: String,
    name: String,
    pub(crate) category: String,
    file_format: String,
    size_bytes: u64,
    reported_architecture: Option<String>,
    pub(crate) validation: String,
    note: String,
    display_name: Option<String>,
    pub(crate) family: Option<String>,
    family_source: String,
    license: Option<String>,
    notes: Option<String>,
    integrity_state: String,
    recorded_sha256: Option<String>,
    potential_duplicate_ids: Vec<String>,
}

fn load_registry(root: &Path, filename: &str) -> Value {
    let path = root.join(filename);
    if path.is_symlink() { return Value::Null; }
    match fs::metadata(&path) {
        Ok(metadata) if metadata.len() <= MAX_REGISTRY => {
            let Ok(data) = fs::read(path) else { return Value::Null };
            let Ok(value) = serde_json::from_slice::<Value>(&data) else { return Value::Null };
            if value.get("schema_version").and_then(Value::as_u64) == Some(1)
                && value.get("models").is_some_and(Value::is_object)
                && value["models"].as_object().is_some_and(|v| v.len() <= MAX_ENTRIES * 3)
            {
                value
            } else { Value::Null }
        }
        _ => Value::Null,
    }
}

fn reported_architecture(path: &Path, size: u64) -> (Option<String>, bool) {
    if size < 10 { return (None, false); }
    let Ok(mut file) = File::open(path) else { return (None, false) };
    let mut first = [0_u8; 8];
    if file.read_exact(&mut first).is_err() { return (None, false) }
    let len = u64::from_le_bytes(first);
    if len < 2 || len > MAX_HEADER || len > size - 8 { return (None, false); }
    let mut bytes = vec![0_u8; len as usize];
    if file.read_exact(&mut bytes).is_err() { return (None, false); }
    let Ok(header) = serde_json::from_slice::<Value>(&bytes) else { return (None, false) };
    if !header.is_object() { return (None, false); }
    let metadata = header.get("__metadata__");
    if metadata.is_some_and(|v| !v.is_object()) { return (None, false); }
    let label = metadata.and_then(|v| v.get("modelspec.architecture")
        .or_else(|| v.get("ss_base_model_version")))
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty() && s.len() <= 128)
        .map(ToString::to_string);
    (label, true)
}

fn family_from_architecture(label: Option<&str>) -> Option<&'static str> {
    let lower = label?.trim().to_ascii_lowercase();
    if lower.starts_with("stable-diffusion-xl-v1")
        || lower.starts_with("stable-diffusion-xl-turbo")
        || lower.starts_with("sdxl_base") || lower == "sdxl"
    { return Some("sdxl"); }
    if lower.starts_with("stable-diffusion-v1") || lower.starts_with("sd_v1") { return Some("sd15"); }
    if lower.starts_with("stable-diffusion-v2") || lower.starts_with("sd_v2") { return Some("sd2"); }
    if lower.starts_with("stable-diffusion-v3") || lower.starts_with("stable-diffusion-3") { return Some("sd3"); }
    if lower.starts_with("flux.1") || lower.starts_with("flux-1") { return Some("flux"); }
    None
}

fn metadata_str(value: &Value, field: &str, limit: usize) -> Option<String> {
    value.get(field).and_then(Value::as_str)
        .filter(|s| !s.is_empty() && s.chars().count() <= limit)
        .map(ToString::to_string)
}

pub(crate) fn scan_native_models(root: &Path) -> Result<Vec<ModelRecord>, String> {
    if root.is_symlink() { return Err("Unsafe model directory".into()); }
    if !root.is_dir() { return Ok(vec![]); }
    let annotations = load_registry(root, "annotations.json");
    let integrity = load_registry(root, "integrity.json");
    let mut result = Vec::new();

    for (dir_name, category) in [("checkpoints", "checkpoint"), ("loras", "lora"), ("vae", "vae")] {
        let folder = root.join(dir_name);
        if folder.is_symlink() || !folder.is_dir() { continue; }
        let mut files: Vec<_> = fs::read_dir(folder)
            .map_err(|e| e.to_string())?
            .filter_map(Result::ok).collect();
        files.sort_by_key(|entry| entry.file_name());
        for entry in files.iter().take(MAX_ENTRIES) {
            let path = entry.path();
            let Ok(info) = fs::symlink_metadata(&path) else { continue; };
            if info.file_type().is_symlink() || !info.file_type().is_file() { continue; }
            let Some(name) = path.file_name().and_then(|s| s.to_str()) else { continue; };
            let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("").to_ascii_lowercase();
            if ext != "safetensors" && ext != "ckpt" { continue; }
            let id = format!("{dir_name}/{name}");
            let (arch, valid) = if ext == "safetensors" {
                reported_architecture(&path, info.len())
            } else { (None, false) };
            let (validation, note) = if ext == "ckpt" {
                ("blocked_legacy", "CKPT 자동 로딩이 차단됩니다.")
            } else if !valid {
                ("invalid_header", "safetensors 헤더가 손상되었거나 인식되지 않습니다.")
            } else {
                ("metadata_only", "헤더만 읽었습니다. 모델 로딩과 호환성은 검증하지 않았습니다.")
            };
            let annotation = &annotations["models"][&id];
            let manual = metadata_str(annotation, "family_override", 12)
                .filter(|x| matches!(x.as_str(), "sd15" | "sd2" | "sdxl" | "sd3" | "flux"));
            let inferred = family_from_architecture(arch.as_deref()).map(ToString::to_string);
            let family_source = if manual.is_some() { "manual" }
                else if inferred.is_some() { "header" } else { "unknown" };
            let family = manual.or(inferred);

            let snapshot = &integrity["models"][id.as_str()];
            let digest = metadata_str(snapshot, "sha256", 64)
                .filter(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()));
            let (state, hash) = if ext != "safetensors" || digest.is_none() {
                ("not_recorded", None)
            } else {
                let size_ok = snapshot["size_bytes"].as_u64() == Some(info.len());
                let mtime_ok = info.modified().ok()
                    .and_then(|d| d.duration_since(std::time::UNIX_EPOCH).ok())
                    .map(|d| d.as_nanos())
                    == snapshot["mtime_ns"].as_u64().map(u128::from);
                if size_ok && mtime_ok {
                    ("snapshot_unchanged", digest)
                } else { ("file_changed", digest) }
            };

            result.push(ModelRecord {
                id, name: name.to_owned(), category: category.to_owned(),
                file_format: ext, size_bytes: info.len(), reported_architecture: arch,
                validation: validation.to_owned(), note: note.to_owned(),
                display_name: metadata_str(annotation, "display_name", 96),
                family, family_source: family_source.to_owned(),
                license: metadata_str(annotation, "license", 120),
                notes: metadata_str(annotation, "notes", 400),
                integrity_state: state.to_owned(), recorded_sha256: hash,
                potential_duplicate_ids: vec![],
            });
        }
    }
    // Both files must still match their registration-time mtime/size snapshot.
    for i in 0..result.len() {
        if result[i].integrity_state != "snapshot_unchanged" { continue; }
        let Some(hash) = result[i].recorded_sha256.clone() else { continue; };
        let current_id = result[i].id.clone();
        let candidates: Vec<String> = result.iter().filter(|item|
            item.id != current_id
                && item.integrity_state == "snapshot_unchanged"
                && item.recorded_sha256.as_deref() == Some(hash.as_str())
        ).map(|item| item.id.clone()).collect();
        result[i].potential_duplicate_ids = candidates;
    }
    Ok(result)
}

#[tauri::command]
pub async fn list_local_models(app: tauri::AppHandle) -> Result<Vec<ModelRecord>, String> {
    let root = super::model_import::model_root(&app)?;
    tauri::async_runtime::spawn_blocking(move || scan_native_models(&root))
        .await.map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn file(path: &Path, family: &str) {
        let header = serde_json::json!({"__metadata__": {"modelspec.architecture": family}}).to_string();
        let mut f = File::create(path).unwrap();
        f.write_all(&(header.len() as u64).to_le_bytes()).unwrap();
        f.write_all(header.as_bytes()).unwrap();
        f.write_all(&[0, 0, 0, 0]).unwrap();
    }

    #[test]
    fn native_catalog_handles_known_model_and_legacy_without_loading_weights() {
        let temp = tempfile::tempdir().unwrap();
        let folder = temp.path().join("checkpoints");
        fs::create_dir(&folder).unwrap();
        file(&folder.join("sample.safetensors"), "stable-diffusion-xl-v1-base");
        fs::write(folder.join("old.ckpt"), b"pickle contents are never executed").unwrap();
        let models = scan_native_models(temp.path()).unwrap();
        assert_eq!(models.len(), 2);
        assert_eq!(models.iter().find(|x| x.name == "sample.safetensors").unwrap().family.as_deref(), Some("sdxl"));
        assert_eq!(models.iter().find(|x| x.name == "old.ckpt").unwrap().validation, "blocked_legacy");
    }

    #[test]
    fn native_catalog_rejects_bad_headers_and_ignores_missing_folders() {
        let temp = tempfile::tempdir().unwrap();
        let folder = temp.path().join("loras");
        fs::create_dir(&folder).unwrap();
        fs::write(folder.join("bad.safetensors"), b"invalid").unwrap();
        let models = scan_native_models(temp.path()).unwrap();
        assert_eq!(models.len(), 1);
        assert_eq!(models[0].validation, "invalid_header");
    }

    #[test]
    fn manual_registration_does_not_prove_compatibility() {
        let temp = tempfile::tempdir().unwrap();
        let folder = temp.path().join("loras");
        fs::create_dir(&folder).unwrap();
        file(&folder.join("style.safetensors"), "unknown");
        let a = serde_json::json!({"schema_version": 1,
            "models":{"loras/style.safetensors":{"display_name":"Style","family_override":"sdxl"}}});
        fs::write(temp.path().join("annotations.json"), a.to_string()).unwrap();
        let models = scan_native_models(temp.path()).unwrap();
        assert_eq!(models[0].family_source, "manual");
        assert_eq!(models[0].family.as_deref(), Some("sdxl"));
        assert_eq!(models[0].display_name.as_deref(), Some("Style"));
    }
}
