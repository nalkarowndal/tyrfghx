//! Native, user-initiated file picker + local safetensors import.
//! Only the model CATEGORY crosses the webview/Rust boundary. A path cannot be
//! supplied to this command, even by a compromised webview.

use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File},
    io::{Read, Write},
    path::{Path, PathBuf},
    time::{Duration, Instant},
    thread,
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

// Reject a final-component Windows reparse point on the *opened handle*
// instead of trusting only a prior path-based is_symlink check. Ancestor
// reparse paths and malicious concurrent filesystem mutation remain outside
// this narrowly scoped safeguard.
#[cfg(windows)]
fn open_source_file(source: &Path) -> Result<File, String> {
    use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
    const FILE_FLAG_OPEN_REPARSE_POINT: u32 = 0x0020_0000;
    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0400;
    let input = fs::OpenOptions::new()
        .read(true)
        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
        .open(source)
        .map_err(|e| e.to_string())?;
    let metadata = input.metadata().map_err(|e| e.to_string())?;
    if !metadata.is_file()
        || metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
    {
        return Err("Source reparse point or nonregular file rejected".into());
    }
    Ok(input)
}

#[cfg(not(windows))]
fn open_source_file(source: &Path) -> Result<File, String> {
    let input = File::open(source).map_err(|e| e.to_string())?;
    if !input.metadata().map_err(|e| e.to_string())?.is_file() {
        return Err("Source must be a regular file".into());
    }
    Ok(input)
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

// Same exact cooperative directory lock used by backend/model_manifest_lock.py.
// This stops two cooperating processes from losing each other's JSON writes,
// but is NOT a hostile-filesystem/ACL/race-free guarantee. A crash leaves
// a lock directory requiring explicit user repair; never auto-break it.
struct ManifestWriteGuard {
    path: PathBuf,
}

impl ManifestWriteGuard {
    fn acquire(root: &Path) -> Result<Self, String> {
        let lock = root.join(".integrity-write.lockdir");
        let start = Instant::now();
        loop {
            match fs::create_dir(&lock) {
                Ok(()) => return Ok(Self { path: lock }),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                    // One metadata snapshot, rather than multiple path
                    // queries which can disagree during a normal release.
                    match fs::symlink_metadata(&lock) {
                        Ok(meta) if meta.file_type().is_dir() => {}
                        Ok(_) => return Err("Unsafe integrity registry lock".into()),
                        Err(err) if err.kind() == std::io::ErrorKind::NotFound => continue,
                        Err(err) => return Err(err.to_string()),
                    }
                    if start.elapsed() >= Duration::from_secs(10) {
                        return Err("Integrity registry busy; inspect stale lock manually".into());
                    }
                    thread::sleep(Duration::from_millis(25));
                }
                Err(error) => return Err(error.to_string()),
            }
        }
    }
}

impl Drop for ManifestWriteGuard {
    fn drop(&mut self) {
        let _ = fs::remove_dir(&self.path);
    }
}

fn validate_existing_manifest(root: &Path) -> Result<(), String> {
    let path = root.join("integrity.json");
    if path.is_symlink() {
        return Err("Unsafe manifest symlink".into());
    }
    if path.exists() {
        if fs::metadata(&path).map_err(|e| e.to_string())?.len() > MAX_MANIFEST {
            return Err("Integrity registry too large".into());
        }
        let data: serde_json::Value = serde_json::from_slice(
            &fs::read(&path).map_err(|e| e.to_string())?
        ).map_err(|_| "Damaged integrity registry")?;
        if data.get("schema_version").and_then(|x| x.as_u64()) != Some(1)
            || !data.get("models").is_some_and(|x| x.is_object()) {
            return Err("Invalid integrity registry schema".into());
        }
    }
    Ok(())
}

fn record_snapshot(root: &Path, id: &str, hash: &str, size: u64, mtime: u64) -> Result<(), String> {
    let _write_guard = ManifestWriteGuard::acquire(root)?;
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

    let mut input = open_source_file(source)?;
    let source_info = input.metadata().map_err(|e| e.to_string())?;
    check_header(&mut input, source_info.len())?;
    use std::io::Seek;
    input.rewind().map_err(|e| e.to_string())?;

    ensure_real_directory(root)?;
    let dest_folder = root.join(category);
    ensure_real_directory(&dest_folder)?;
    validate_existing_manifest(root)?;
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
        // Never unlink a user-visible pathname on rollback. Another process
        // may have replaced it after our no-clobber publish. Keeping an
        // unregistered copy is safer than deleting somebody else's file.
        return Err(format!("Model copy retained; manifest registration failed: {error}"));
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

    #[cfg(windows)]
    #[test]
    fn native_handle_rejects_test_symlink_source_without_following() {
        use std::os::windows::fs::symlink_file;
        let root = tempfile::tempdir().unwrap();
        let original = root.path().join("original.safetensors");
        example_file(&original);
        let contents = fs::read(&original).unwrap();
        let link = root.path().join("linked.safetensors");
        match symlink_file(&original, &link) {
            Ok(()) => {
                assert!(open_source_file(&link).is_err());
                assert!(import_selected_file(&link, "loras", &root.path().join("models")).is_err());
                assert_eq!(fs::read(&original).unwrap(), contents);
            }
            Err(e) if e.kind() == std::io::ErrorKind::PermissionDenied => {
                // Some Windows CI runners cannot create developer symlinks.
            }
            Err(e) => panic!("unexpected temporary symlink setup failure: {e}"),
        }
    }

    #[test]
    fn concurrent_native_imports_keep_every_registry_entry() {
        use std::sync::{Arc, Barrier};
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("models");
        let gate = Arc::new(Barrier::new(6));
        let mut threads = Vec::new();
        for i in 0..6 {
            let path = temp.path().join(format!("concurrent_{i}.safetensors"));
            example_file(&path);
            let shared_root = root.clone();
            let ready = Arc::clone(&gate);
            threads.push(std::thread::spawn(move || {
                ready.wait();
                import_selected_file(&path, "loras", &shared_root)
            }));
        }
        for thread in threads {
            assert!(thread.join().unwrap().is_ok());
        }
        let text = fs::read_to_string(root.join("integrity.json")).unwrap();
        let manifest: serde_json::Value = serde_json::from_str(&text).unwrap();
        let entries = manifest["models"].as_object().unwrap();
        assert_eq!(entries.len(), 6);
        for i in 0..6 {
            assert!(entries.contains_key(&format!("loras/concurrent_{i}.safetensors")));
        }
        assert!(!root.join(".integrity-write.lockdir").exists());
    }


    // An actual independent Python 3.12 child imports the same lock module
    // used by the Python CLI, while this Rust process uses ManifestWriteGuard.
    // The test touches only a disposable tmp directory, not user models.
    #[cfg(windows)]
    #[test]
    fn windows_python_and_rust_manifest_lock_interoperate() {
        use std::process::{Command, Stdio};
        use std::sync::mpsc::{self, RecvTimeoutError};

        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path().join("models");
        fs::create_dir(&root).unwrap();
        let backend = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend");

        const PY_HOLDS_LOCK: &str = r#"
import pathlib, sys, time
sys.path.insert(0, sys.argv[2])
from model_manifest_lock import exclusive_manifest_write
root = pathlib.Path(sys.argv[1])
with exclusive_manifest_write(root):
    (root / "python-held.flag").write_text("acquired")
    deadline = time.monotonic() + 7
    while not (root / "rust-release.flag").exists():
        if time.monotonic() > deadline:
            raise TimeoutError("Rust did not release cross-language lock test")
        time.sleep(0.02)
"#;
        let mut py = Command::new("python")
            .args(["-u", "-c", PY_HOLDS_LOCK])
            .arg(&root).arg(&backend)
            .stdout(Stdio::null()).stderr(Stdio::piped())
            .spawn().expect("Python 3.12 must be installed by Windows Rust CI");
        let mut ready = false;
        for _ in 0..250 {
            if root.join("python-held.flag").exists() {
                ready = true;
                break;
            }
            if py.try_wait().unwrap().is_some() {
                break;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        assert!(ready, "Python did not acquire the shared manifest guard");

        let writer_root = root.clone();
        let (tx, rx) = mpsc::channel();
        let thread = std::thread::spawn(move || {
            let result = record_snapshot(
                &writer_root, "loras/cross-process.safetensors",
                &"a".repeat(64), 128, 42,
            );
            tx.send(result).unwrap();
        });
        assert!(matches!(
            rx.recv_timeout(Duration::from_millis(175)),
            Err(RecvTimeoutError::Timeout)
        ), "Rust writer bypassed Python's held lock");
        fs::write(root.join("rust-release.flag"), b"go").unwrap();
        assert!(rx.recv_timeout(Duration::from_secs(6)).unwrap().is_ok());
        thread.join().unwrap();
        let output = py.wait_with_output().unwrap();
        assert!(output.status.success(), "Python holder failed: {}",
                String::from_utf8_lossy(&output.stderr));
        assert!(!root.join(".integrity-write.lockdir").exists());

        const PY_WAITS_ON_RUST: &str = r#"
import pathlib, sys
sys.path.insert(0, sys.argv[2])
from model_manifest_lock import exclusive_manifest_write
root = pathlib.Path(sys.argv[1])
with exclusive_manifest_write(root):
    (root / "python-after-rust.flag").write_text("acquired")
"#;
        let held = ManifestWriteGuard::acquire(&root).unwrap();
        let child = Command::new("python")
            .args(["-u", "-c", PY_WAITS_ON_RUST])
            .arg(&root).arg(&backend)
            .stdout(Stdio::null()).stderr(Stdio::piped())
            .spawn().unwrap();
        std::thread::sleep(Duration::from_millis(200));
        assert!(!root.join("python-after-rust.flag").exists(),
                "Python bypassed Rust's held manifest lock");
        drop(held);
        let output = child.wait_with_output().unwrap();
        assert!(output.status.success(), "Python writer failed: {}",
                String::from_utf8_lossy(&output.stderr));
        assert!(root.join("python-after-rust.flag").exists());
        assert!(!root.join(".integrity-write.lockdir").exists());
        let manifest: serde_json::Value = serde_json::from_slice(
            &fs::read(root.join("integrity.json")).unwrap()
        ).unwrap();
        assert!(manifest["models"]["loras/cross-process.safetensors"].is_object());
    }

    #[test]
    fn broken_registry_is_rejected_before_model_is_published() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("models");
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("integrity.json"), b"{broken").unwrap();
        let source = temp.path().join("safe.safetensors");
        example_file(&source);
        assert!(import_selected_file(&source, "loras", &root).is_err());
        assert!(!root.join("loras/safe.safetensors").exists());
        assert_eq!(fs::read(root.join("integrity.json")).unwrap(), b"{broken");
    }

}
