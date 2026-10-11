//! Agentic OS desktop shell.
//!
//! Debug builds expect the backend to be started by `npm run dev:desktop` and only report its
//! URL. Release builds spawn the bundled backend sidecar on a free port and wait for its
//! `AGENTIC_OS_READY {"port": N}` line (ADR 0002).
//!
//! The sidecar is never killed from here: it watches this process (`--parent-pid`) and shuts
//! down by itself as soon as we exit. Killing it would terminate the PyInstaller bootloader
//! before it can delete its `_MEI*` extraction folder in %TEMP%.

use std::sync::Mutex;

use tauri::{Manager, State};

/// Error returned by `backend_url` while the sidecar is still booting. Anything else is final.
const STARTING: &str = "starting";

#[derive(Default)]
struct Backend {
    url: Mutex<Option<String>>,
    error: Mutex<Option<String>>,
}

impl Backend {
    fn fail(&self, error: impl Into<String>) {
        *self.url.lock().unwrap() = None;
        *self.error.lock().unwrap() = Some(error.into());
    }
}

/// URL of the backend. Errors with "starting" until the sidecar is ready (the UI retries);
/// any other error is permanent.
#[tauri::command]
fn backend_url(backend: State<'_, Backend>) -> Result<String, String> {
    if let Some(url) = backend.url.lock().unwrap().clone() {
        return Ok(url);
    }
    if let Some(error) = backend.error.lock().unwrap().clone() {
        return Err(error);
    }
    Err(STARTING.into())
}

#[cfg(debug_assertions)]
fn start_backend(app: &tauri::AppHandle) -> Result<(), String> {
    let url = std::env::var("AGENTIC_OS_BACKEND_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8765".to_string());
    *app.state::<Backend>().url.lock().unwrap() = Some(url);
    Ok(())
}

#[cfg_attr(debug_assertions, allow(dead_code))]
fn parse_ready(line: &str) -> Option<u16> {
    let payload = line.trim().strip_prefix("AGENTIC_OS_READY")?;
    let value: serde_json::Value = serde_json::from_str(payload.trim()).ok()?;
    value
        .get("port")?
        .as_u64()
        .and_then(|port| u16::try_from(port).ok())
}

#[cfg(not(debug_assertions))]
fn start_backend(app: &tauri::AppHandle) -> Result<(), String> {
    use tauri_plugin_shell::{process::CommandEvent, ShellExt};

    let parent_pid = std::process::id().to_string();
    let (mut events, _child) = app
        .shell()
        .sidecar("agentic-os-backend")
        .map_err(|e| e.to_string())?
        .args(["--port", "0", "--parent-pid", parent_pid.as_str()])
        .spawn()
        .map_err(|e| e.to_string())?;

    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            let backend = handle.state::<Backend>();
            match event {
                CommandEvent::Stdout(line) => {
                    if let Some(port) = parse_ready(&String::from_utf8_lossy(&line)) {
                        *backend.url.lock().unwrap() = Some(format!("http://127.0.0.1:{port}"));
                    }
                }
                // Backend logs go to its own log file (data_dir/logs/backend.log).
                CommandEvent::Terminated(status) => {
                    backend.fail(format!("backend exited (code {:?})", status.code));
                }
                CommandEvent::Error(error) => backend.fail(error),
                _ => {}
            }
        }
    });
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .manage(Backend::default())
        .invoke_handler(tauri::generate_handler![backend_url])
        .setup(|app| {
            // A missing or blocked sidecar must not crash the window: report it to the UI.
            if let Err(error) = start_backend(app.handle()) {
                app.state::<Backend>()
                    .fail(format!("backend failed to start: {error}"));
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Agentic OS");
}

#[cfg(test)]
mod tests {
    use super::{parse_ready, Backend, STARTING};

    #[test]
    fn parses_ready_line() {
        assert_eq!(
            parse_ready("AGENTIC_OS_READY {\"port\": 51234}\r\n"),
            Some(51234)
        );
    }

    #[test]
    fn ignores_other_lines() {
        assert_eq!(parse_ready("INFO: Uvicorn running"), None);
        assert_eq!(parse_ready("AGENTIC_OS_READY not-json"), None);
        assert_eq!(parse_ready("AGENTIC_OS_READY {\"port\": 99999}"), None);
    }

    #[test]
    fn failure_clears_url_and_is_not_starting() {
        let backend = Backend::default();
        *backend.url.lock().unwrap() = Some("http://127.0.0.1:1".into());
        backend.fail("backend exited (code Some(1))");
        assert!(backend.url.lock().unwrap().is_none());
        assert_ne!(backend.error.lock().unwrap().as_deref(), Some(STARTING));
    }
}
