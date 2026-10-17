//! M3-2 read-only preview of images created by the explicit M3-1 local CLI.
//! No arbitrary frontend-supplied paths, no asset-protocol scope, no process execution.

use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::Serialize;
use std::{fs, path::{Path, PathBuf}, time::UNIX_EPOCH};
use tauri::AppHandle;

const MAX_IMAGE_BYTES: u64 = 8 * 1024 * 1024;
const MAX_IMAGES: usize = 4;
const MAX_SCAN: usize = 500;
const PNG_SIGNATURE: &[u8] = b"\x89PNG\r\n\x1a\n";

#[derive(Serialize)]
pub struct GenerationPreview {
    pub id: String,
    pub image_src: String,
    pub size_bytes: u64,
}

fn is_known_name(name: &str) -> bool {
    name.len() == "aiimage-".len() + 32 + ".png".len()
        && name.starts_with("aiimage-")
        && name.ends_with(".png")
        && name["aiimage-".len()..name.len() - 4]
            .bytes().all(|c| c.is_ascii_hexdigit())
}

fn image_root(app: &AppHandle) -> Result<PathBuf, String> {
    let model_root = super::model_import::model_root(app)?;
    let parent = model_root.parent().ok_or("Cannot resolve app storage directory")?;
    Ok(parent.join("outputs"))
}

fn list_previews(root: &Path) -> Result<Vec<GenerationPreview>, String> {
    if root.is_symlink() { return Err("Unsafe output directory".to_string()); }
    if !root.is_dir() { return Ok(vec![]); }
    let mut candidates = Vec::new();
    for item in fs::read_dir(root).map_err(|e| e.to_string())?.take(MAX_SCAN) {
        let Ok(entry) = item else { continue };
        let path = entry.path();
        let Ok(info) = fs::symlink_metadata(&path) else { continue };
        if !info.file_type().is_file() || info.file_type().is_symlink()
            || info.len() < PNG_SIGNATURE.len() as u64 || info.len() > MAX_IMAGE_BYTES {
            continue;
        }
        let Some(name) = entry.file_name().to_str().map(str::to_owned) else { continue };
        if !is_known_name(&name) { continue; }
        let stamp = info.modified().ok().and_then(|d| d.duration_since(UNIX_EPOCH).ok())
            .map(|d| d.as_millis()).unwrap_or(0);
        candidates.push((stamp, name, path, info.len()));
    }
    // Deterministic newest-first ordering, bounded preview count before read.
    candidates.sort_by(|a,b| b.0.cmp(&a.0).then_with(|| a.1.cmp(&b.1)));
    let mut result = Vec::new();
    for (_, name, path, expected_size) in candidates.into_iter().take(MAX_IMAGES) {
        let Ok(bytes) = fs::read(&path) else { continue };
        if bytes.len() as u64 != expected_size || !bytes.starts_with(PNG_SIGNATURE) { continue; }
        result.push(GenerationPreview {
            id: name,
            image_src: format!("data:image/png;base64,{}", STANDARD.encode(bytes)),
            size_bytes: expected_size,
        });
    }
    Ok(result)
}

#[tauri::command]
pub async fn list_generation_previews(app: AppHandle) -> Result<Vec<GenerationPreview>, String> {
    let root = image_root(&app)?;
    tauri::async_runtime::spawn_blocking(move || list_previews(&root))
        .await.map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fake_png(root: &Path, id: &str) {
        fs::write(root.join(id), [PNG_SIGNATURE, b"fixture payload"].concat()).unwrap();
    }

    #[test]
    fn only_reads_generated_png_names() {
        let dir = tempfile::tempdir().unwrap();
        let id = format!("aiimage-{}.png", "a".repeat(32));
        fake_png(dir.path(), &id);
        fake_png(dir.path(), "other.png");
        fs::write(dir.path().join(format!("aiimage-{}.png", "b".repeat(32))), b"invalid").unwrap();
        assert_eq!(list_previews(dir.path()).unwrap().len(), 1);
        let image = &list_previews(dir.path()).unwrap()[0];
        assert_eq!(image.id, id);
        assert!(image.image_src.starts_with("data:image/png;base64,"));
    }

    #[test]
    fn ignores_missing_and_symlinked_outputs() {
        let dir = tempfile::tempdir().unwrap();
        assert!(list_previews(&dir.path().join("missing")).unwrap().is_empty());
        let outside = tempfile::tempdir().unwrap();
        let source = outside.path().join(format!("aiimage-{}.png", "f".repeat(32)));
        fs::write(&source, PNG_SIGNATURE).unwrap();
        #[cfg(windows)]
        let linked = dir.path().join(source.file_name().unwrap());
        #[cfg(windows)]
        if std::os::windows::fs::symlink_file(&source, &linked).is_ok() {
            assert!(list_previews(dir.path()).unwrap().is_empty());
        }
    }

    #[test]
    fn caps_preview_count_and_rejects_oversized_file() {
        let dir = tempfile::tempdir().unwrap();
        for i in 0..8 {
            fake_png(dir.path(), &format!("aiimage-{:032x}.png", i));
        }
        let images = list_previews(dir.path()).unwrap();
        assert_eq!(images.len(), MAX_IMAGES);
        let big = dir.path().join(format!("aiimage-{}.png", "b".repeat(32)));
        let file = fs::File::create(big).unwrap();
        file.set_len(MAX_IMAGE_BYTES + 1).unwrap();
        assert_eq!(list_previews(dir.path()).unwrap().len(), MAX_IMAGES);
    }
}
