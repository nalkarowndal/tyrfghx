mod model_import;
mod model_catalog;
mod model_integrity;
mod generation_gallery;
mod generation_jobs;
mod generation_result;
mod windows_process_job;
mod gpu_diagnostics;
mod vram_safety;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(generation_jobs::JobManager::default())
        .invoke_handler(tauri::generate_handler![model_import::import_local_model, model_catalog::list_local_models, model_integrity::verify_local_model_hash, generation_gallery::list_generation_previews, generation_jobs::local_generation_supported, generation_jobs::start_local_generation, generation_jobs::check_local_generation_vram, generation_jobs::generation_job_status, generation_jobs::cancel_local_generation, gpu_diagnostics::inspect_local_gpu])
        ;
    // No embedded HTTP server exists in normal builds (feature absent).
    // Even in a specially compiled E2E build, activation requires two
    // explicit environment variables from an operator-owned CI runner.
    #[cfg(feature = "e2e-webdriver")]
    let builder = {
        let enabled = std::env::var("AIIMAGE_E2E_ENABLE").as_deref() == Ok("1");
        let port_is_valid = std::env::var("TAURI_WEBDRIVER_PORT")
            .ok().and_then(|port| port.parse::<u16>().ok())
            .map(|port| port >= 1024).unwrap_or(false);
        if enabled && port_is_valid {
            builder.plugin(tauri_plugin_wdio_webdriver::init())
        } else {
            builder
        }
    };
    builder
        .run(tauri::generate_context!())
        .expect("failed to run aiimage");
}
