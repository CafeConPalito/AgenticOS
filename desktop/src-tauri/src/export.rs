//! «Exportar» in the desktop app (phase 21): WebView2 ignores `<a download>` with a blob, so the
//! exported agents, themes and CSVs are written from here. The path comes from the native save
//! dialog opened by this same command, never from the page: the UI cannot write anywhere else.

use tauri_plugin_dialog::DialogExt;

/// Opens «Guardar como» with `name` and writes `contents` there. The chosen path, or `None` if
/// the user cancelled. Async so the blocking dialog runs off the main thread.
#[tauri::command]
pub async fn save_file(
    app: tauri::AppHandle,
    name: String,
    contents: String,
    filter: String,
    extensions: Vec<String>,
) -> Result<Option<String>, String> {
    let extensions: Vec<&str> = extensions.iter().map(String::as_str).collect();
    let Some(chosen) = app
        .dialog()
        .file()
        .set_file_name(file_name(&name))
        .add_filter(filter, &extensions)
        .blocking_save_file()
    else {
        return Ok(None);
    };
    let path = chosen.into_path().map_err(|e| e.to_string())?;
    std::fs::write(&path, contents).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(Some(path.display().to_string()))
}

/// The suggested name without any folder in it: only the dialog decides where.
fn file_name(name: &str) -> &str {
    name.rsplit(['/', '\\']).next().unwrap_or(name)
}

#[cfg(test)]
mod tests {
    use super::file_name;

    #[test]
    fn the_suggested_name_carries_no_folder() {
        assert_eq!(file_name("Redactor.agent.json"), "Redactor.agent.json");
        assert_eq!(file_name("..\\..\\Windows\\evil.json"), "evil.json");
        assert_eq!(file_name("a/b/tema.theme.json"), "tema.theme.json");
    }
}
