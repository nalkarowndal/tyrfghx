//! Explicit, read-only SHA-256 verification for an already registered local model.
//! No model weights are interpreted, no arbitrary paths accepted, and no
//! integrity manifest updates are performed. A match is point-in-time only.

use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::Read;
use std::path::Path;

const MAX_FILE: u64 = 64 * 1024 * 1024 * 1024;
const MAX_MANIFEST: u64 = 1_048_576;
const BUFFER_SIZE: usize = 1024 * 1024;

#[derive(Debug, Serialize, PartialEq)]
pub struct HashCheck {
    /// match, mismatch or not_recorded (not a GPU or compatibility verdict).
    pub status: String,
}

fn parse_model_id(id: &str) -> Result<(&str, &str), String> {
    if id.len() > 512 || id.contains('\\') || id.contains(':') || id.contains('\0') {
        return Err("허용되지 않은 모델 식별자입니다.".into());
    }
    let (category, filename) = id.split_once('/')
        .ok_or("허용되지 않은 모델 식별자입니다.")?;
    if !matches!(category, "checkpoints" | "loras" | "vae")
        || filename.is_empty() || filename == "." || filename == ".."
        || filename.contains('/') || !filename.to_ascii_lowercase().ends_with(".safetensors")
    {
        return Err("허용되지 않은 모델 식별자입니다.".into());
    }
    Ok((category, filename))
}

fn verify_at_root(root: &Path, model_id: &str) -> Result<HashCheck, String> {
    let (category, filename) = parse_model_id(model_id)?;
    if root.is_symlink() || !root.is_dir() {
        return Err("모델 저장 폴더가 없거나 안전하지 않습니다.".into());
    }
    let folder = root.join(category);
    if folder.is_symlink() || !folder.is_dir() {
        return Err("모델 종류 폴더가 없거나 안전하지 않습니다.".into());
    }

    // Read only the fixed, bounded registry. No unregistered files are hashed.
    let manifest = root.join("integrity.json");
    if manifest.is_symlink() {
        return Err("무결성 기록 파일이 안전하지 않습니다.".into());
    }
    let meta = match fs::metadata(&manifest) {
        Ok(info) => info,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound =>
            return Ok(HashCheck { status: "not_recorded".into() }),
        Err(_) => return Err("무결성 기록 파일을 읽을 수 없습니다.".into()),
    };
    if !meta.is_file() || meta.len() > MAX_MANIFEST {
        return Err("무결성 기록 파일을 읽을 수 없습니다.".into());
    }
    let data = fs::read(&manifest).map_err(|_| "무결성 기록 파일을 읽을 수 없습니다.")?;
    let manifest_data: Value = serde_json::from_slice(&data)
        .map_err(|_| "무결성 기록 형식이 잘못되었습니다.")?;
    if manifest_data["schema_version"].as_u64() != Some(1)
        || !manifest_data["models"].is_object()
    {
        return Err("무결성 기록 형식이 잘못되었습니다.".into());
    }
    let Some(expected) = manifest_data["models"][model_id]["sha256"].as_str() else {
        return Ok(HashCheck { status: "not_recorded".into() });
    };
    if expected.len() != 64 || !expected.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("등록된 체크섬 형식이 올바르지 않습니다.".into());
    }

    let path = folder.join(filename);
    let info = fs::symlink_metadata(&path)
        .map_err(|_| "모델 파일을 찾을 수 없습니다.")?;
    if info.file_type().is_symlink() || !info.file_type().is_file()
        || info.len() < 10 || info.len() > MAX_FILE
    {
        return Err("모델 파일 형식이나 크기를 확인할 수 없습니다.".into());
    }
    let mut file = File::open(&path).map_err(|_| "모델 파일을 읽을 수 없습니다.")?;
    let before = file.metadata().map_err(|_| "모델 파일 정보를 읽을 수 없습니다.")?;
    if !before.is_file() || before.len() != info.len() {
        return Err("검사 중 모델 파일이 변경되었습니다.".into());
    }
    let mut hasher = Sha256::new();
    let mut buffer = vec![0u8; BUFFER_SIZE];
    let mut total = 0u64;
    loop {
        let count = file.read(&mut buffer).map_err(|_| "모델 해시를 읽을 수 없습니다.")?;
        if count == 0 { break; }
        total += count as u64;
        if total > MAX_FILE { return Err("허용된 모델 크기를 초과했습니다.".into()); }
        hasher.update(&buffer[..count]);
    }
    let after = file.metadata().map_err(|_| "모델 파일 정보를 읽을 수 없습니다.")?;
    if total != before.len() || before.len() != after.len()
        || before.modified().ok() != after.modified().ok()
        || path.is_symlink()
    {
        return Err("검사 중 모델 파일이 변경되었습니다.".into());
    }
    let actual = format!("{:x}", hasher.finalize());
    Ok(HashCheck {
        status: if actual.eq_ignore_ascii_case(expected) { "match" } else { "mismatch" }.into(),
    })
}

#[tauri::command]
pub async fn verify_local_model_hash(app: tauri::AppHandle, model_id: String) -> Result<HashCheck, String> {
    parse_model_id(&model_id)?;
    let root = super::model_import::model_root(&app)?;
    tauri::async_runtime::spawn_blocking(move || verify_at_root(&root, &model_id))
        .await.map_err(|_| "모델 검증 작업이 중단되었습니다.".to_owned())?
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn sample(root: &Path) -> (std::path::PathBuf, String) {
        let dir = root.join("loras");
        fs::create_dir(&dir).unwrap();
        let path = dir.join("sample.safetensors");
        let header = br#"{"__metadata__":{}}"#;
        let mut file = File::create(&path).unwrap();
        file.write_all(&(header.len() as u64).to_le_bytes()).unwrap();
        file.write_all(header).unwrap();
        file.write_all(&[1, 2, 3, 4]).unwrap();
        drop(file);
        let hash = format!("{:x}", Sha256::digest(fs::read(&path).unwrap()));
        let registry = serde_json::json!({"schema_version":1,
            "models":{"loras/sample.safetensors":{"sha256":hash}}});
        fs::write(root.join("integrity.json"), registry.to_string()).unwrap();
        (path, hash)
    }

    #[test]
    fn verifies_actual_bytes_including_same_size_tampering() {
        let tmp = tempfile::tempdir().unwrap();
        let (path, _) = sample(tmp.path());
        assert_eq!(verify_at_root(tmp.path(), "loras/sample.safetensors").unwrap().status, "match");
        let mut bytes = fs::read(&path).unwrap();
        *bytes.last_mut().unwrap() ^= 1;
        fs::write(&path, bytes).unwrap();
        assert_eq!(verify_at_root(tmp.path(), "loras/sample.safetensors").unwrap().status, "mismatch");
    }

    #[test]
    fn never_hashes_unregistered_or_unsafe_ids() {
        let tmp = tempfile::tempdir().unwrap();
        sample(tmp.path());
        assert_eq!(verify_at_root(tmp.path(), "loras/other.safetensors").unwrap().status, "not_recorded");
        for id in ["../secret.safetensors", "loras/../secret.safetensors",
            "loras\\sample.safetensors", "loras/C:sample.safetensors", "loras/sample.ckpt",
            "/sample.safetensors", "loras/folder/sample.safetensors"] {
            assert!(verify_at_root(tmp.path(), id).is_err(), "{id}");
        }
    }

    #[test]
    fn rejects_corrupt_manifest_and_missing_file() {
        let tmp = tempfile::tempdir().unwrap();
        let (path, _) = sample(tmp.path());
        fs::remove_file(path).unwrap();
        assert!(verify_at_root(tmp.path(), "loras/sample.safetensors").is_err());
        fs::write(tmp.path().join("integrity.json"), b"{bad json").unwrap();
        assert!(verify_at_root(tmp.path(), "loras/sample.safetensors").is_err());
    }

    #[cfg(unix)]
    #[test]
    fn blocks_symlinked_model_file() {
        use std::os::unix::fs::symlink;
        let tmp = tempfile::tempdir().unwrap();
        let (path, _) = sample(tmp.path());
        let original = tmp.path().join("original.safetensors");
        fs::rename(&path, &original).unwrap();
        symlink(&original, path).unwrap();
        assert!(verify_at_root(tmp.path(), "loras/sample.safetensors").is_err());
    }
}
