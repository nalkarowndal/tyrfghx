mod model_import;
mod model_catalog;
mod generation_gallery;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![model_import::import_local_model, model_catalog::list_local_models, generation_gallery::list_generation_previews])
        .run(tauri::generate_context!())
        .expect("failed to run aiimage");
}
