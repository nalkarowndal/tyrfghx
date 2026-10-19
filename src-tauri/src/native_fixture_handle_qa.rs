//! M4-1h: Win32 handle-based REPARSE QA on *temporary synthetic fixtures*.
//!
//! This module is test-only, not reachable via a Tauri command or the
//! production FastAPI process. It opens no real user wheel/model files.
//! Checking only the final component does NOT validate all ancestor directory
//! reparse points or protect against malicious concurrent path replacement.
#![cfg(all(test, windows))]

use std::{
    ffi::OsStr,
    os::windows::ffi::OsStrExt,
    path::Path,
    ptr,
};
use windows_sys::Win32::{
    Foundation::{CloseHandle, HANDLE, INVALID_HANDLE_VALUE},
    Storage::FileSystem::{
        CreateFileW, GetFileInformationByHandleEx, GetFinalPathNameByHandleW,
        FileAttributeTagInfo, FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_REPARSE_POINT,
        FILE_ATTRIBUTE_TAG_INFO, FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT,
        FILE_READ_ATTRIBUTES, FILE_SHARE_DELETE, FILE_SHARE_READ, FILE_SHARE_WRITE,
        OPEN_EXISTING,
    },
};

struct OwnedFileHandle(HANDLE);

impl Drop for OwnedFileHandle {
    fn drop(&mut self) {
        if !self.0.is_null() && self.0 != INVALID_HANDLE_VALUE {
            unsafe { CloseHandle(self.0) };
        }
    }
}

fn to_utf16(path: &OsStr) -> Result<Vec<u16>, &'static str> {
    let wide: Vec<u16> = path.encode_wide().collect();
    if wide.is_empty() || wide.len() > 30_000 || wide.contains(&0) {
        return Err("invalid_fixture_path");
    }
    Ok(wide.into_iter().chain([0]).collect())
}

fn open_reparse_point_itself(path: &Path, is_dir: bool) -> Result<OwnedFileHandle, &'static str> {
    let wide = to_utf16(path.as_os_str())?;
    let flags = FILE_FLAG_OPEN_REPARSE_POINT
        | if is_dir { FILE_FLAG_BACKUP_SEMANTICS } else { 0 };
    let handle = unsafe {
        CreateFileW(
            wide.as_ptr(),
            FILE_READ_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            ptr::null(),
            OPEN_EXISTING,
            flags,
            ptr::null_mut(),
        )
    };
    if handle.is_null() || handle == INVALID_HANDLE_VALUE {
        return Err("fixture_open_denied");
    }
    Ok(OwnedFileHandle(handle))
}

fn attribute_tag(handle: &OwnedFileHandle) -> Result<FILE_ATTRIBUTE_TAG_INFO, &'static str> {
    let mut out = FILE_ATTRIBUTE_TAG_INFO::default();
    let ok = unsafe {
        GetFileInformationByHandleEx(
            handle.0,
            FileAttributeTagInfo,
            &mut out as *mut _ as *mut _,
            std::mem::size_of::<FILE_ATTRIBUTE_TAG_INFO>() as u32,
        )
    };
    if ok == 0 {
        return Err("fixture_attributes_denied");
    }
    Ok(out)
}

fn final_handle_path(handle: &OwnedFileHandle) -> Result<String, &'static str> {
    let mut buffer = [0u16; 1024];
    let used = unsafe {
        GetFinalPathNameByHandleW(handle.0, buffer.as_mut_ptr(), buffer.len() as u32, 0)
    } as usize;
    if used == 0 || used >= buffer.len() {
        return Err("fixture_path_denied");
    }
    let final_name = String::from_utf16(&buffer[..used]).map_err(|_| "fixture_path_denied")?;
    if !final_name.starts_with(r"\\?\") {
        return Err("fixture_path_denied");
    }
    Ok(final_name)
}

fn verify_plain_directory(path: &Path) -> Result<OwnedFileHandle, &'static str> {
    let handle = open_reparse_point_itself(path, true)?;
    let attrs = attribute_tag(&handle)?;
    if attrs.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0
        || attrs.FileAttributes & FILE_ATTRIBUTE_DIRECTORY == 0
    {
        return Err("fixture_reparse_denied");
    }
    Ok(handle)
}

/// Metadata-only Win32 QA, scoped to two fixed **synthetic** basenames.
/// No file content read, process execution, installation, or GPU access.
fn inspect_test_child(root: &Path, basename: &str) -> Result<(), &'static str> {
    if !root.is_absolute() || !matches!(basename, "sample.whl" | "fixture.marker") {
        return Err("invalid_fixture_path");
    }
    let root_handle = verify_plain_directory(root)?;
    let root_final = final_handle_path(&root_handle)?;
    // Never accept caller-computed paths. The directory and child are opened
    // as handles and the latter's final path must match the expected child.
    let candidate = root.join(basename);
    let child = open_reparse_point_itself(&candidate, false)?;
    let attrs = attribute_tag(&child)?;
    if attrs.FileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT) != 0 {
        return Err("fixture_reparse_denied");
    }
    let child_final = final_handle_path(&child)?;
    let expected = format!("{}\\{basename}", root_final.trim_end_matches('\\'));
    if !child_final.eq_ignore_ascii_case(&expected) {
        return Err("fixture_parent_denied");
    }
    Ok(())
}

#[test]
fn regular_temporary_mock_and_marker_have_independent_win32_handles() {
    let root = tempfile::tempdir().unwrap();
    std::fs::write(root.path().join("fixture.marker"), b"synthetic only").unwrap();
    std::fs::write(root.path().join("sample.whl"), b"fake package data").unwrap();
    assert_eq!(inspect_test_child(root.path(), "fixture.marker"), Ok(()));
    assert_eq!(inspect_test_child(root.path(), "sample.whl"), Ok(()));
    assert_eq!(std::fs::read(root.path().join("sample.whl")).unwrap(), b"fake package data");
}

#[test]
fn unknown_or_traversal_basename_and_missing_file_fail_closed() {
    let root = tempfile::tempdir().unwrap();
    assert_eq!(inspect_test_child(root.path(), "..\\outside"), Err("invalid_fixture_path"));
    assert_eq!(inspect_test_child(root.path(), "../sample.whl"), Err("invalid_fixture_path"));
    assert_eq!(inspect_test_child(root.path(), "sample.whl"), Err("fixture_open_denied"));
    assert_eq!(inspect_test_child(Path::new("relative"), "sample.whl"), Err("invalid_fixture_path"));
}

#[test]
fn child_symlink_is_rejected_by_open_reparse_point_flag() {
    use std::os::windows::fs::symlink_file;
    let root = tempfile::tempdir().unwrap();
    let external = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(external.path(), b"external fixture content").unwrap();
    match symlink_file(external.path(), root.path().join("sample.whl")) {
        Ok(()) => {
            assert_eq!(inspect_test_child(root.path(), "sample.whl"), Err("fixture_reparse_denied"));
            assert_eq!(std::fs::read(external.path()).unwrap(), b"external fixture content");
        }
        Err(err) if err.kind() == std::io::ErrorKind::PermissionDenied => {
            // Windows runner without Developer Mode: no symlink was made.
        }
        Err(err) => panic!("unexpected synthetic symlink setup failure: {err}"),
    }
}

#[test]
fn root_directory_symlink_is_rejected() {
    use std::os::windows::fs::symlink_dir;
    let outer = tempfile::tempdir().unwrap();
    let real = outer.path().join("real");
    std::fs::create_dir(&real).unwrap();
    std::fs::write(real.join("sample.whl"), b"fake").unwrap();
    let alias = outer.path().join("alias");
    match symlink_dir(&real, &alias) {
        Ok(()) => assert_eq!(inspect_test_child(&alias, "sample.whl"), Err("fixture_reparse_denied")),
        Err(err) if err.kind() == std::io::ErrorKind::PermissionDenied => {}
        Err(err) => panic!("unexpected synthetic directory symlink setup failure: {err}"),
    }
}
