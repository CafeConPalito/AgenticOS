//! Agentic OS desktop shell.
//!
//! Debug builds expect the backend to be started by `npm run dev:desktop` and only report its
//! URL. Release builds spawn the bundled backend sidecar on a free port and wait for its
//! `AGENTIC_OS_READY {"port": N}` line (ADR 0002), and launch it again if it exits
//! (`sidecar.rs`, ADR 0012). Only one instance of the release app runs at a time.
//!
//! The sidecar is never killed from here: it watches this process (`--parent-pid`) and shuts
//! down by itself as soon as we exit. Killing it would terminate the PyInstaller bootloader
//! before it can delete its `_MEI*` extraction folder in %TEMP%.

mod sidecar;

use std::sync::Mutex;
use std::time::Instant;

use tauri::{Manager, State};

/// Error returned by `backend_url` while the sidecar is (re)starting. Anything else is final.
const STARTING: &str = "starting";

#[derive(Default)]
struct Backend {
    url: Mutex<Option<String>>,
    error: Mutex<Option<String>>,
    supervisor: Mutex<Supervisor>,
}

/// The sidecar's lifecycle, for the restarts.
#[derive(Default)]
struct Supervisor {
    running: bool,
    failures: u32,
    ready_at: Option<Instant>,
}

impl Backend {
    fn fail(&self, error: impl Into<String>) {
        *self.url.lock().unwrap() = None;
        *self.error.lock().unwrap() = Some(error.into());
    }

    /// Back to «starting»: the UI keeps asking for the URL until the new backend is ready.
    fn restarting(&self) {
        *self.url.lock().unwrap() = None;
        *self.error.lock().unwrap() = None;
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

/// «Reintentar» after the backend gave up: a new attempt with the failure count at zero.
#[tauri::command]
fn restart_backend(app: tauri::AppHandle) -> Result<(), String> {
    let backend = app.state::<Backend>();
    {
        let mut supervisor = backend.supervisor.lock().unwrap();
        if supervisor.running {
            return Ok(());
        }
        supervisor.failures = 0;
    }
    backend.restarting();
    start_backend(&app)
}

/// «Abrir logs»: the backend's logs folder in the file manager (it works with the backend down).
#[tauri::command]
fn open_logs() -> Result<(), String> {
    let folder = sidecar::logs_dir(sidecar::home_dir());
    std::fs::create_dir_all(&folder).map_err(|e| e.to_string())?;
    #[cfg(windows)]
    let program = "explorer";
    #[cfg(target_os = "macos")]
    let program = "open";
    #[cfg(all(unix, not(target_os = "macos")))]
    let program = "xdg-open";
    std::process::Command::new(program)
        .arg(&folder)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
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
    {
        let backend = app.state::<Backend>();
        let mut supervisor = backend.supervisor.lock().unwrap();
        supervisor.running = true;
        supervisor.ready_at = None;
    }

    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            let backend = handle.state::<Backend>();
            match event {
                CommandEvent::Stdout(line) => {
                    if let Some(port) = parse_ready(&String::from_utf8_lossy(&line)) {
                        *backend.url.lock().unwrap() = Some(format!("http://127.0.0.1:{port}"));
                        backend.supervisor.lock().unwrap().ready_at = Some(Instant::now());
                    }
                }
                // Backend logs go to its own log file (data_dir/logs/backend.log).
                CommandEvent::Terminated(status) => {
                    on_exit(&handle, status.code);
                    return;
                }
                CommandEvent::Error(error) => backend.fail(error),
                _ => {}
            }
        }
    });
    Ok(())
}

/// The sidecar exited: launch it again, or give up after too many failures in a row.
#[cfg(not(debug_assertions))]
fn on_exit(app: &tauri::AppHandle, code: Option<i32>) {
    let backend = app.state::<Backend>();
    let action = {
        let mut supervisor = backend.supervisor.lock().unwrap();
        supervisor.running = false;
        if supervisor
            .ready_at
            .is_some_and(|at| at.elapsed() >= sidecar::STABLE_AFTER)
        {
            supervisor.failures = 0;
        }
        let (action, failures) = sidecar::next_action(code, supervisor.failures);
        supervisor.failures = failures;
        action
    };
    match action {
        sidecar::Action::GiveUp => backend.fail(format!("backend exited (code {code:?})")),
        sidecar::Action::Restart(delay) => {
            backend.restarting();
            let handle = app.clone();
            tauri::async_runtime::spawn_blocking(move || {
                std::thread::sleep(delay);
                if let Err(error) = start_backend(&handle) {
                    handle
                        .state::<Backend>()
                        .fail(format!("backend failed to start: {error}"));
                }
            });
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default();
    // Two instances would run two backends on the same database. Release only, so the
    // development build can run next to the installed app. It must be the first plugin.
    #[cfg(not(debug_assertions))]
    let builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.unminimize();
            let _ = window.show();
            let _ = window.set_focus();
        }
    }));
    builder
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .manage(Backend::default())
        .invoke_handler(tauri::generate_handler![
            backend_url,
            restart_backend,
            open_logs
        ])
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

    #[test]
    fn restarting_is_starting_again() {
        let backend = Backend::default();
        backend.fail("backend exited (code Some(1))");
        backend.restarting();
        assert!(backend.url.lock().unwrap().is_none());
        assert!(backend.error.lock().unwrap().is_none());
    }
}
