mod model_import;
mod model_catalog;
mod model_integrity;
mod generation_gallery;
mod generation_jobs;
mod generation_result;
mod windows_process_job;
mod gpu_diagnostics;
mod vram_safety;
mod backend_runtime;

// CPU-only Win32 subprocess/pipe QA; compiled into tests ONLY.
#[cfg(all(test, windows))]
mod inference_worker_stdio_qa;

// The embedded HTTP test server must never activate by a Cargo feature alone.
// Validate the complete opt-in policy independently of Tauri or network I/O.
#[cfg(any(test, feature = "e2e-webdriver"))]
fn embedded_webdriver_authorized(enable: Option<&str>, port: Option<&str>) -> bool {
    enable == Some("1")
        && port
            .and_then(|raw| raw.parse::<u16>().ok())
            .is_some_and(|value| value >= 1024)
}

#[cfg(test)]
mod embedded_driver_policy_tests {
    use super::embedded_webdriver_authorized;

    #[test]
    fn rejects_partial_missing_or_invalid_runtime_opt_in() {
        for (enable, port) in [
            (None, None),
            (Some("1"), None),
            (None, Some("4445")),
            (Some("0"), Some("4445")),
            (Some("true"), Some("4445")),
            (Some("1"), Some("0")),
            (Some("1"), Some("1023")),
            (Some("1"), Some("not-a-port")),
            (Some("1"), Some("65536")),
            (Some("1 "), Some("4445")),
        ] {
            assert!(!embedded_webdriver_authorized(enable, port));
        }
    }

    #[test]
    fn accepts_only_explicit_enable_with_unprivileged_numeric_port() {
        assert!(embedded_webdriver_authorized(Some("1"), Some("4445")));
        assert!(embedded_webdriver_authorized(Some("1"), Some("65535")));
        assert!(embedded_webdriver_authorized(Some("1"), Some("1024")));
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(generation_jobs::JobManager::default())
        .manage(backend_runtime::BackendState::default())
        .invoke_handler(tauri::generate_handler![backend_runtime::bundled_backend_enabled, backend_runtime::backend_status, backend_runtime::restart_backend, model_import::import_local_model, model_catalog::list_local_models, model_integrity::verify_local_model_hash, generation_gallery::list_generation_previews, generation_jobs::local_generation_supported, generation_jobs::start_local_generation, generation_jobs::check_local_generation_vram, generation_jobs::generation_job_status, generation_jobs::cancel_local_generation, gpu_diagnostics::inspect_local_gpu])
        ;
    // No embedded HTTP server exists in normal builds (feature absent).
    // Even in a specially compiled E2E build, activation requires two
    // explicit environment variables from an operator-owned CI runner.
    #[cfg(feature = "e2e-webdriver")]
    let builder = {
        let enable = std::env::var("AIIMAGE_E2E_ENABLE").ok();
        let port = std::env::var("TAURI_WEBDRIVER_PORT").ok();
        if embedded_webdriver_authorized(enable.as_deref(), port.as_deref()) {
            builder.plugin(tauri_plugin_wdio_webdriver::init())
        } else {
            builder
        }
    };
    builder
        .build(tauri::generate_context!())
        .expect("failed to build aiimage")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) { backend_runtime::shutdown(app); }
        });
}
