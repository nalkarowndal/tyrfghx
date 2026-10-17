mod model_import;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![model_import::import_local_model])
        .run(tauri::generate_context!())
        .expect("failed to run aiimage");
}
