mod model_import;
mod model_catalog;
mod generation_gallery;
mod generation_jobs;
mod generation_result;
mod windows_process_job;
mod gpu_diagnostics;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(generation_jobs::JobManager::default())
        .invoke_handler(tauri::generate_handler![model_import::import_local_model, model_catalog::list_local_models, generation_gallery::list_generation_previews, generation_jobs::local_generation_supported, generation_jobs::start_local_generation, generation_jobs::generation_job_status, generation_jobs::cancel_local_generation, gpu_diagnostics::inspect_local_gpu])
        .run(tauri::generate_context!())
        .expect("failed to run aiimage");
}
