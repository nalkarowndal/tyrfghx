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
    path::{Component, Path, Prefix},
    ptr,
};
use windows_sys::Win32::{
    Foundation::{CloseHandle, HANDLE, INVALID_HANDLE_VALUE},
    Storage::FileSystem::{
        CreateFileW, GetFileInformationByHandle, GetFileInformationByHandleEx,
        GetFinalPathNameByHandleW, BY_HANDLE_FILE_INFORMATION,
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

/// Stable within this fixture test while the file handle remains open.
/// Neither the path string nor the file name is used as a file identity.
/// This is *not* an endorsement of all filesystem/volume ID semantics.
#[derive(Clone, Copy, Debug, Hash, PartialEq, Eq)]
struct TestObjectIdentity {
    volume_serial: u32,
    file_index: u64,
}

fn identity_and_link_count(
    handle: &OwnedFileHandle,
) -> Result<(TestObjectIdentity, u32), &'static str> {
    let mut info = BY_HANDLE_FILE_INFORMATION::default();
    if unsafe { GetFileInformationByHandle(handle.0, &mut info) } == 0 {
        return Err("fixture_identity_denied");
    }
    // Be conservative about an uninformative filesystem result.
    if info.nNumberOfLinks == 0 {
        return Err("fixture_identity_denied");
    }
    Ok((
        TestObjectIdentity {
            volume_serial: info.dwVolumeSerialNumber,
            file_index: (u64::from(info.nFileIndexHigh) << 32)
                | u64::from(info.nFileIndexLow),
        },
        info.nNumberOfLinks,
    ))
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

/// Reject UNC, device namespace, verbatim, drive-relative and dot-parent
/// fixture paths BEFORE any file handles are acquired.  This is a narrow
/// synthetic-only drive-local test policy, not general Windows path policy.
fn validate_synthetic_drive_root(root: &Path) -> Result<(), &'static str> {
    if !root.is_absolute() {
        return Err("invalid_fixture_path");
    }
    let mut parts = root.components();
    if !matches!(parts.next(), Some(Component::Prefix(prefix))
                 if matches!(prefix.kind(), Prefix::Disk(_)))
        || !matches!(parts.next(), Some(Component::RootDir))
        || parts.any(|part| !matches!(part, Component::Normal(_)))
    {
        return Err("invalid_fixture_path");
    }
    Ok(())
}

/// Open and retain native handles for each ancestor including the drive root
/// and the synthetic fixture directory. The test rejects symlink/junction
/// *components* and checks each child's final handle path versus its parent.
/// The opens are still path-based (NOT NtCreateFile handle-relative), so this
/// is a negative-regression test, NOT adversarial race-free production safety.
fn inspect_synthetic_ancestor_chain(
    root: &Path,
) -> Result<Vec<OwnedFileHandle>, &'static str> {
    validate_synthetic_drive_root(root)?;
    let components: Vec<_> = root.ancestors()
        .filter(|ancestor| ancestor.is_absolute())
        .collect();
    if components.is_empty() || components.len() > 32 {
        return Err("invalid_fixture_path");
    }
    let mut opened = Vec::with_capacity(components.len());
    let mut seen_identities = std::collections::HashSet::new();
    for directory in components.into_iter().rev() {
        let handle = verify_plain_directory(directory)?;
        let (identity, _) = identity_and_link_count(&handle)?;
        if !seen_identities.insert(identity) {
            return Err("fixture_identity_denied");
        }
        // Check every native handle independently. Windows can normalize
        // short-name/volume aliases differently across adjacent components;
        // comparing adjacent *display path strings* incorrectly rejects
        // ordinary temp directories. Retain the actual handles instead.
        let _ = final_handle_path(&handle)?;
        opened.push(handle);
    }
    Ok(opened)
}

/// Metadata-only Win32 QA, scoped to two fixed **synthetic** basenames.
/// No file content read, process execution, installation, or GPU access.
fn inspect_test_child(root: &Path, basename: &str) -> Result<(), &'static str> {
    if !matches!(basename, "sample.whl" | "fixture.marker") {
        return Err("invalid_fixture_path");
    }
    let opened_ancestors = inspect_synthetic_ancestor_chain(root)?;
    let root_handle = opened_ancestors.last().ok_or("invalid_fixture_path")?;
    let root_final = final_handle_path(root_handle)?;
    // Never accept caller-computed paths. The directory and child are opened
    // as handles and the latter's final path must match the expected child.
    let candidate = root.join(basename);
    let child = open_reparse_point_itself(&candidate, false)?;
    let attrs = attribute_tag(&child)?;
    if attrs.FileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT) != 0 {
        return Err("fixture_reparse_denied");
    }
    let (child_id, hardlink_count) = identity_and_link_count(&child)?;
    let (root_id, _) = identity_and_link_count(root_handle)?;
    if child_id == root_id || hardlink_count != 1 {
        return Err("fixture_identity_denied");
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

#[test]
fn nested_synthetic_fixture_checks_each_ancestor_and_keeps_success() {
    let parent = tempfile::tempdir().unwrap();
    let one = parent.path().join("normal");
    let two = one.join("nested");
    std::fs::create_dir(&one).unwrap();
    std::fs::create_dir(&two).unwrap();
    std::fs::write(two.join("sample.whl"), b"synthetic").unwrap();
    assert_eq!(inspect_test_child(&two, "sample.whl"), Ok(()));
}

#[test]
fn traversing_grandparent_symlink_is_rejected() {
    use std::os::windows::fs::symlink_dir;
    let parent = tempfile::tempdir().unwrap();
    let real = parent.path().join("real-directory");
    let nested = real.join("nested");
    std::fs::create_dir(&real).unwrap();
    std::fs::create_dir(&nested).unwrap();
    std::fs::write(nested.join("sample.whl"), b"synthetic").unwrap();

    let alias = parent.path().join("aliased-parent");
    match symlink_dir(&real, &alias) {
        Ok(()) => {
            // Root and file are plain objects, but an ancestor is a link.
            assert_eq!(
                inspect_test_child(&alias.join("nested"), "sample.whl"),
                Err("fixture_reparse_denied")
            );
            assert_eq!(std::fs::read(nested.join("sample.whl")).unwrap(), b"synthetic");
        }
        Err(err) if err.kind() == std::io::ErrorKind::PermissionDenied => {
            // Not all Windows CI workers permit creating symlink fixtures.
        }
        Err(err) => panic!("unexpected synthetic grandparent link setup failure: {err}"),
    }
}

#[test]
fn rejects_parent_traversal_unc_and_device_namespaces_before_opening() {
    let directory = tempfile::tempdir().unwrap();
    assert_eq!(
        inspect_test_child(&directory.path().join("nested").join(".."), "sample.whl"),
        Err("invalid_fixture_path")
    );
    for unsafe_root in [
        r"\\server\share\synthetic",
        r"\\?\C:\synthetic",
        r"\\.\C:\synthetic",
        r"C:drive-relative\synthetic",
    ] {
        assert_eq!(inspect_test_child(Path::new(unsafe_root), "sample.whl"),
                   Err("invalid_fixture_path"));
    }
}

#[test]
fn component_walk_does_not_expose_a_tauri_command_or_modify_files() {
    let folder = tempfile::tempdir().unwrap();
    let target = folder.path().join("sample.whl");
    std::fs::write(&target, b"read-only test fixture").unwrap();
    assert_eq!(inspect_test_child(folder.path(), "sample.whl"), Ok(()));
    assert_eq!(std::fs::read(&target).unwrap(), b"read-only test fixture");
}

#[test]
fn two_handles_to_same_mock_have_same_kernel_identity() {
    let fixture = tempfile::tempdir().unwrap();
    let sample = fixture.path().join("sample.whl");
    std::fs::write(&sample, b"synthetic bytes only").unwrap();
    let first = open_reparse_point_itself(&sample, false).unwrap();
    let second = open_reparse_point_itself(&sample, false).unwrap();
    let (a, a_links) = identity_and_link_count(&first).unwrap();
    let (b, b_links) = identity_and_link_count(&second).unwrap();
    assert_eq!(a, b);
    assert_eq!(a_links, 1);
    assert_eq!(b_links, 1);
    assert_eq!(inspect_test_child(fixture.path(), "sample.whl"), Ok(()));
}

#[test]
fn distinct_mock_files_have_different_kernel_identity() {
    let fixture = tempfile::tempdir().unwrap();
    let sample = fixture.path().join("sample.whl");
    let marker = fixture.path().join("fixture.marker");
    std::fs::write(&sample, b"mock wheel").unwrap();
    std::fs::write(&marker, b"mock marker").unwrap();
    let first = open_reparse_point_itself(&sample, false).unwrap();
    let second = open_reparse_point_itself(&marker, false).unwrap();
    let (a, _) = identity_and_link_count(&first).unwrap();
    let (b, _) = identity_and_link_count(&second).unwrap();
    assert_ne!(a, b);
}

#[test]
fn hardlink_to_synthetic_fixture_is_denied_without_touching_target() {
    let fixture = tempfile::tempdir().unwrap();
    let original = fixture.path().join("original.bin");
    std::fs::write(&original, b"hardlink target bytes").unwrap();
    let alias = fixture.path().join("sample.whl");
    match std::fs::hard_link(&original, &alias) {
        Ok(()) => {
            let alias_handle = open_reparse_point_itself(&alias, false).unwrap();
            let (identity, links) = identity_and_link_count(&alias_handle).unwrap();
            assert!(links >= 2);
            let original_handle = open_reparse_point_itself(&original, false).unwrap();
            assert_eq!(identity, identity_and_link_count(&original_handle).unwrap().0);
            assert_eq!(
                inspect_test_child(fixture.path(), "sample.whl"),
                Err("fixture_identity_denied")
            );
            assert_eq!(std::fs::read(&original).unwrap(), b"hardlink target bytes");
        }
        Err(err) if matches!(err.kind(), std::io::ErrorKind::PermissionDenied
            | std::io::ErrorKind::Unsupported) => {
            // Filesystem or runner does not support this disposable hardlink.
        }
        Err(err) => panic!("unexpected local synthetic hardlink setup failure: {err}"),
    }
}

#[test]
fn no_path_authorization_from_matching_identity_alone() {
    let fixture = tempfile::tempdir().unwrap();
    let original = fixture.path().join("original.bin");
    std::fs::write(&original, b"not an authorized basename").unwrap();
    assert_eq!(
        inspect_test_child(fixture.path(), "original.bin"),
        Err("invalid_fixture_path")
    );
    assert_eq!(std::fs::read(&original).unwrap(), b"not an authorized basename");
}
