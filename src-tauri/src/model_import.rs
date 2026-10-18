//! Native, user-initiated file picker + local safetensors import.
//! Only the model CATEGORY crosses the webview/Rust boundary. A path cannot be
//! supplied to this command, even by a compromised webview.

use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File},
    io::{Read, Write},
    path::{Path, PathBuf},
};
use tauri::{AppHandle, Manager};
use tauri_plugin_dialog::DialogExt;

const MAX_HEADER: u64 = 1_048_576;
const MAX_FILE: u64 = 64 * 1024 * 1024 * 1024;
const MAX_MANIFEST: u64 = 1_048_576;
const CHUNK: usize = 4 * 1024 * 1024;

#[derive(Serialize)]
pub struct ImportResult {
    pub model_id: String,
    pub sha256: String,
    pub size_bytes: u64,
}

fn allowed_category(name: &str) -> Result<&str, String> {
    match name {
        "checkpoints" | "loras" | "vae" => Ok(name),
        _ => Err("Unsupported model category".into()),
    }
}

fn ensure_real_directory(path: &Path) -> Result<(), String> {
    if path.is_symlink() {
        return Err("Symbolic-link directories are not supported".into());
    }
    fs::create_dir_all(path).map_err(|e| e.to_string())?;
    if path.is_symlink() || !path.is_dir() {
        return Err("Unsafe model directory".into());
    }
    Ok(())
}

fn check_header(source: &mut File, size: u64) -> Result<(), String> {
    if size < 10 || size > MAX_FILE {
        return Err("Model size is invalid or exceeds 64 GiB".into());
    }
    let mut bytes = [0_u8; 8];
    source.read_exact(&mut bytes).map_err(|e| e.to_string())?;
    let header_len = u64::from_le_bytes(bytes);
    if header_len < 2 || header_len > MAX_HEADER || header_len > size - 8 {
        return Err("Invalid or oversized safetensors header".into());
    }
    let mut header = vec![0_u8; header_len as usize];
    source.read_exact(&mut header).map_err(|e| e.to_string())?;
    let value: serde_json::Value =
        serde_json::from_slice(&header).map_err(|_| "Invalid safetensors JSON header")?;
    if !value.is_object() {
        return Err("Invalid safetensors object header".into());
    }
    Ok(())
}

fn record_snapshot(root: &Path, id: &str, hash: &str, size: u64, mtime: u64) -> Result<(), String> {
    let manifest = root.join("integrity.json");
    if manifest.is_symlink() {
        return Err("Integrity manifest symlink blocked".into());
    }
    let mut data = if manifest.exists() {
        if fs::metadata(&manifest).map_err(|e| e.to_string())?.len() > MAX_MANIFEST {
            return Err("Integrity registry too large".into());
        }
        let bytes = fs::read(&manifest).map_err(|e| e.to_string())?;
        let parsed: serde_json::Value =
            serde_json::from_slice(&bytes).map_err(|_| "Damaged integrity registry")?;
        if parsed.get("schema_version").and_then(|x| x.as_i64()) != Some(1)
            || !parsed.get("models").is_some_and(|x| x.is_object())
        {
            return Err("Invalid integrity registry schema".into());
        }
        parsed
    } else {
        serde_json::json!({"schema_version": 1, "models": {}})
    };
    data["models"][id] = serde_json::json!({
        "sha256": hash,
        "size_bytes": size,
        "mtime_ns": mtime
    });
    let payload = serde_json::to_vec_pretty(&data).map_err(|e| e.to_string())?;
    if payload.len() as u64 > MAX_MANIFEST {
        return Err("Integrity registry size limit exceeded".into());
    }
    let mut staged = tempfile::Builder::new().prefix(".integrity-").tempfile_in(root)
        .map_err(|e| e.to_string())?;
    staged.write_all(&payload).map_err(|e| e.to_string())?;
    staged.as_file().sync_all().map_err(|e| e.to_string())?;
    staged.persist(&manifest).map_err(|e| e.error.to_string())?;
    Ok(())
}

fn import_selected_file(source: &Path, category: &str, root: &Path) -> Result<ImportResult, String> {
    let category = allowed_category(category)?;
    if source.is_symlink() || !source.is_file() {
        return Err("Source must be a regular file and not a symlink".into());
    }
    let name = source.file_name().and_then(|x| x.to_str())
        .ok_or("Invalid model file name")?;
    if name.contains('/') || name.contains('\\') || name.contains(':') || name == "." || name == ".."
        || !name.to_lowercase().ends_with(".safetensors")
    {
        return Err("Only named .safetensors files may be imported".into());
    }

    let mut input = File::open(source).map_err(|e| e.to_string())?;
    let source_info = input.metadata().map_err(|e| e.to_string())?;
    check_header(&mut input, source_info.len())?;
    use std::io::Seek;
    input.rewind().map_err(|e| e.to_string())?;

    ensure_real_directory(root)?;
    let dest_folder = root.join(category);
    ensure_real_directory(&dest_folder)?;
    let dest = dest_folder.join(name);
    if dest.exists() || dest.is_symlink() {
        return Err("A model with the same name already exists; refusing overwrite".into());
    }
    let mut staging = tempfile::Builder::new().prefix(".import-").suffix(".tmp")
        .tempfile_in(&dest_folder).map_err(|e| e.to_string())?;
    let mut sha = Sha256::new();
    let mut copied = 0_u64;
    let mut block = vec![0_u8; CHUNK];
    loop {
        let read = input.read(&mut block).map_err(|e| e.to_string())?;
        if read == 0 { break; }
        copied += read as u64;
        if copied > MAX_FILE { return Err("Model exceeds size limit".into()); }
        sha.update(&block[..read]);
        staging.write_all(&block[..read]).map_err(|e| e.to_string())?;
    }
    if copied != source_info.len() {
        return Err("Source changed during import".into());
    }
    staging.as_file().sync_all().map_err(|e| e.to_string())?;
    let hash = format!("{:x}", sha.finalize());
    // persist_noclobber refuses to replace existing model paths.
    let imported = staging.persist_noclobber(&dest).map_err(|e| e.error.to_string())?;
    let saved = imported.metadata().map_err(|e| e.to_string())?;
    let mtime = saved.modified().map_err(|e| e.to_string())?
        .duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?
        .as_nanos() as u64;
    let id = format!("{category}/{name}");
    if let Err(error) = record_snapshot(root, &id, &hash, copied, mtime) {
        // Do not claim a registered import when its manifest could not be stored.
        let _ = fs::remove_file(&dest);
        return Err(error);
    }
    Ok(ImportResult { model_id: id, sha256: hash, size_bytes: copied })
}

/// Use one storage root for BOTH native catalog and the selected-file importer.
/// In debug builds this intentionally matches the separate Python dev server.
/// In release builds the native Tauri catalog works even with no Python process.
pub(crate) fn model_root(app: &AppHandle) -> Result<PathBuf, String> {
    if cfg!(debug_assertions) {
        Ok(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../models"))
    } else {
        Ok(app.path().app_local_data_dir().map_err(|e| e.to_string())?.join("models"))
    }
}

#[tauri::command]
pub async fn import_local_model(
    app: AppHandle,
    category: String,
) -> Result<Option<ImportResult>, String> {
    allowed_category(&category)?;
    let root = model_root(&app)?;
    // The native dialog is invoked in Rust; no arbitrary source path is
    // accepted from JavaScript.
    let selected = app.dialog().file()
        .set_title("aiimage — Select local safetensors model")
        .add_filter("Safetensors models", &["safetensors"])
        .blocking_pick_file();
    let Some(selected) = selected else { return Ok(None); };
    let source = selected.into_path().map_err(|e| e.to_string())?;
    tauri::async_runtime::spawn_blocking(move || import_selected_file(&source, &category, &root))
        .await.map_err(|e| e.to_string()).and_then(|r| r.map(Some))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn example_file(path: &Path) {
        let header = br#"{"__metadata__":{}}"#;
        let mut output = File::create(path).unwrap();
        output.write_all(&(header.len() as u64).to_le_bytes()).unwrap();
        output.write_all(header).unwrap();
        output.write_all(&[0, 0, 0, 0]).unwrap();
    }
    #[test]
    fn imports_safe_file_without_overwrite() {
        let tmp = tempfile::tempdir().unwrap();
        let source = tmp.path().join("model.safetensors");
        let root = tmp.path().join("models");
        example_file(&source);
        let original = fs::read(&source).unwrap();
        let result = import_selected_file(&source, "loras", &root).unwrap();
        assert_eq!(result.model_id, "loras/model.safetensors");
        assert_eq!(fs::read(&source).unwrap(), original);
        assert_eq!(fs::read(root.join("loras/model.safetensors")).unwrap(), original);
        assert!(root.join("integrity.json").exists());
        assert!(import_selected_file(&source, "loras", &root).is_err());
    }
    #[test]
    fn refuses_bad_header_and_category() {
        let tmp = tempfile::tempdir().unwrap();
        let source = tmp.path().join("model.safetensors");
        fs::write(&source, b"invalid").unwrap();
        assert!(import_selected_file(&source, "checkpoints", &tmp.path().join("models")).is_err());
        example_file(&source);
        assert!(import_selected_file(&source, "../other", &tmp.path().join("models")).is_err());
    }
    /// Cross-module synthetic smoke test: this is real local disk I/O, but no
    /// model loading, GPU access, file picker, Windows GUI or network.
    #[test]
    fn m3_25_import_catalog_rehash_and_same_size_tamper() {
        let temp = tempfile::tempdir().unwrap();
        let source = temp.path().join("sdxl-model.safetensors");
        let root = temp.path().join("models");
        example_file(&source);
        let source_original = fs::read(&source).unwrap();
        let imported = import_selected_file(&source, "checkpoints", &root).unwrap();
        assert_eq!(imported.model_id, "checkpoints/sdxl-model.safetensors");
        assert_eq!(fs::read(&source).unwrap(), source_original);

        let catalog = crate::model_catalog::scan_native_models(&root).unwrap();
        assert_eq!(catalog.len(), 1);
        let item = &catalog[0];
        assert_eq!(item.id, imported.model_id);
        assert_eq!(item.category, "checkpoint");
        assert_eq!(item.validation, "metadata_only");
        let fields = serde_json::to_value(item).unwrap();
        assert_eq!(fields["integrity_state"], "snapshot_unchanged");
        assert_eq!(fields["recorded_sha256"].as_str(), Some(imported.sha256.as_str()));

        let verdict = crate::model_integrity::verify_at_root(&root, &imported.model_id).unwrap();
        assert_eq!(verdict.status, "match");

        // Same-size changes can evade size-only checks. Explicit rehash cannot.
        let destination = root.join(&imported.model_id);
        let mut modified = fs::read(&destination).unwrap();
        *modified.last_mut().unwrap() ^= 0x01;
        fs::write(&destination, &modified).unwrap();
        assert_eq!(
            crate::model_integrity::verify_at_root(&root, &imported.model_id).unwrap().status,
            "mismatch"
        );
        assert_eq!(fs::read(&source).unwrap(), source_original);
        assert!(import_selected_file(&source, "checkpoints", &root).is_err());
        assert_eq!(fs::read(&destination).unwrap(), modified);
    }

    #[test]
    fn m3_25_catalog_registration_and_duplicate_hints_without_hashing_unknown_files() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("models");
        let first = temp.path().join("first.safetensors");
        let second = temp.path().join("second.safetensors");
        example_file(&first);
        example_file(&second); // Same bytes but different model ID.
        let checkpoint = import_selected_file(&first, "checkpoints", &root).unwrap();
        let lora = import_selected_file(&second, "loras", &root).unwrap();
        assert_eq!(checkpoint.sha256, lora.sha256);

        let vae_folder = root.join("vae");
        fs::create_dir(&vae_folder).unwrap();
        example_file(&vae_folder.join("manually-added.safetensors"));
        let catalog = crate::model_catalog::scan_native_models(&root).unwrap();
        assert_eq!(catalog.len(), 3);
        let a = catalog.iter().find(|item| item.id == checkpoint.model_id).unwrap();
        let b = catalog.iter().find(|item| item.id == lora.model_id).unwrap();
        let a_json = serde_json::to_value(a).unwrap();
        let b_json = serde_json::to_value(b).unwrap();
        assert_eq!(a_json["potential_duplicate_ids"][0].as_str(), Some(lora.model_id.as_str()));
        assert_eq!(b_json["potential_duplicate_ids"][0].as_str(), Some(checkpoint.model_id.as_str()));

        let unregistered = "vae/manually-added.safetensors";
        assert!(catalog.iter().any(|item| item.id == unregistered));
        assert_eq!(
            crate::model_integrity::verify_at_root(&root, unregistered).unwrap().status,
            "not_recorded"
        );
        // A legacy file may appear in the catalog but must not be imported
        // or considered a verified safetensors model.
        let legacy = temp.path().join("legacy.ckpt");
        fs::write(&legacy, b"unsafe legacy format").unwrap();
        assert!(import_selected_file(&legacy, "checkpoints", &root).is_err());
        assert!(crate::model_integrity::verify_at_root(&root, "checkpoints/legacy.ckpt").is_err());
    }

}
