//! Agentic OS desktop shell.
//!
//! Debug builds expect the backend to be started by `npm run dev:desktop` and only report its
//! URL. Release builds spawn the bundled backend sidecar on a free port (ADR 0002), wait for its
//! `AGENTIC_OS_READY {"port": N}` line and kill it when the app exits.

use std::sync::Mutex;

use tauri::{Manager, RunEvent, State};

#[cfg(not(debug_assertions))]
use tauri_plugin_shell::process::CommandChild;

#[derive(Default)]
struct Backend {
    url: Mutex<Option<String>>,
    error: Mutex<Option<String>>,
    #[cfg(not(debug_assertions))]
    child: Mutex<Option<CommandChild>>,
}

/// URL of the backend. Errors with "starting" until the sidecar is ready; the UI retries.
#[tauri::command]
fn backend_url(backend: State<'_, Backend>) -> Result<String, String> {
    if let Some(url) = backend.url.lock().unwrap().clone() {
        return Ok(url);
    }
    if let Some(error) = backend.error.lock().unwrap().clone() {
        return Err(error);
    }
    Err("starting".into())
}

#[cfg(debug_assertions)]
fn start_backend(app: &tauri::AppHandle) -> Result<(), Box<dyn std::error::Error>> {
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
fn start_backend(app: &tauri::AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    use tauri_plugin_shell::{process::CommandEvent, ShellExt};

    let parent_pid = std::process::id().to_string();
    let (mut events, child) = app
        .shell()
        .sidecar("agentic-os-backend")?
        .args(["--port", "0", "--parent-pid", parent_pid.as_str()])
        .spawn()?;
    *app.state::<Backend>().child.lock().unwrap() = Some(child);

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
                CommandEvent::Terminated(status) => {
                    *backend.url.lock().unwrap() = None;
                    *backend.error.lock().unwrap() =
                        Some(format!("backend exited (code {:?})", status.code));
                }
                CommandEvent::Error(error) => {
                    *backend.error.lock().unwrap() = Some(error);
                }
                _ => {}
            }
        }
    });
    Ok(())
}

fn stop_backend(_app: &tauri::AppHandle) {
    #[cfg(not(debug_assertions))]
    if let Some(child) = _app.state::<Backend>().child.lock().unwrap().take() {
        let _ = child.kill();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Backend::default())
        .invoke_handler(tauri::generate_handler![backend_url])
        .setup(|app| {
            start_backend(app.handle())?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Agentic OS")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_backend(app);
            }
        });
}

#[cfg(test)]
mod tests {
    use super::parse_ready;

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
}
