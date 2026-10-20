// Limit native app commands to webviews explicitly granted matching
// allow-* permission by src-tauri/capabilities/default.json. Without this
// AppManifest, invoke_handler commands are exposed to every webview.
// Keep this list in lockstep with tauri::generate_handler! in src/lib.rs.
fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(
            tauri_build::AppManifest::new().commands(&[
                "bundled_backend_enabled",
                "backend_status",
                "restart_backend",
                "import_local_model",
                "list_local_models",
                "verify_local_model_hash",
                "list_generation_previews",
                "local_generation_supported",
                "start_local_generation",
                "check_local_generation_vram",
                "generation_job_status",
                "cancel_local_generation",
                "inspect_local_gpu",
            ]),
        ),
    )
    .expect("failed to build restrictive aiimage native command permissions");
}
