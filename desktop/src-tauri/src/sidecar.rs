//! Supervision of the backend sidecar (phase 08, ADR 0012).
//!
//! If the backend exits, it is launched again: right away when it asked for it (exit code 75,
//! e.g. after moving the data folder), otherwise after 1, 2 and 4 s. After three failures in a
//! row the error is final and the UI offers «Reintentar» (`restart_backend`). A backend that
//! was ready for a minute starts the count again.

use std::path::PathBuf;
use std::time::Duration;

/// Exit code of a backend that asks to be started again (`datadir.RESTART_EXIT_CODE`).
pub const RESTART_EXIT_CODE: i32 = 75;
/// Failures in a row before giving up.
pub const MAX_FAILURES: u32 = 3;
/// Time a backend must stay up after its READY line for its next exit to count from zero.
pub const STABLE_AFTER: Duration = Duration::from_secs(60);

#[derive(Debug, PartialEq, Eq)]
pub enum Action {
    Restart(Duration),
    GiveUp,
}

/// What to do when the backend exits with `exit_code`, after `failures` failures in a row
/// (this exit not included). Returns the action and the new failure count.
pub fn next_action(exit_code: Option<i32>, failures: u32) -> (Action, u32) {
    if exit_code == Some(RESTART_EXIT_CODE) {
        return (Action::Restart(Duration::ZERO), failures);
    }
    let failures = failures + 1;
    if failures > MAX_FAILURES {
        return (Action::GiveUp, failures);
    }
    (
        Action::Restart(Duration::from_secs(1 << (failures - 1))),
        failures,
    )
}

/// The backend's logs folder: `<data>/logs`, where the data folder is the one the pointer in
/// `%APPDATA%\AgenticOS\location.json` names (moved by the user) or that home folder.
pub fn logs_dir(home: PathBuf) -> PathBuf {
    let moved = std::fs::read_to_string(home.join("location.json"))
        .ok()
        .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
        .and_then(|value| value.get("data_dir")?.as_str().map(PathBuf::from));
    moved.unwrap_or(home).join("logs")
}

/// `%APPDATA%\AgenticOS` (or `~/.agentic-os`), as the backend's `config.home_dir`.
pub fn home_dir() -> PathBuf {
    match std::env::var_os("APPDATA") {
        Some(base) => PathBuf::from(base).join("AgenticOS"),
        None => dirs_home().join(".agentic-os"),
    }
}

fn dirs_home() -> PathBuf {
    std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_requested_restart_is_immediate_and_not_a_failure() {
        assert_eq!(
            next_action(Some(RESTART_EXIT_CODE), 2),
            (Action::Restart(Duration::ZERO), 2)
        );
    }

    #[test]
    fn failures_back_off_then_give_up() {
        let (first, n) = next_action(Some(1), 0);
        assert_eq!(first, Action::Restart(Duration::from_secs(1)));
        let (second, n) = next_action(None, n);
        assert_eq!(second, Action::Restart(Duration::from_secs(2)));
        let (third, n) = next_action(Some(0), n);
        assert_eq!(third, Action::Restart(Duration::from_secs(4)));
        assert_eq!(next_action(Some(1), n).0, Action::GiveUp);
    }

    #[test]
    fn logs_follow_the_data_pointer() {
        let home = std::env::temp_dir().join(format!("agentic-os-test-{}", std::process::id()));
        std::fs::create_dir_all(&home).unwrap();
        assert_eq!(logs_dir(home.clone()), home.join("logs"));
        std::fs::write(home.join("location.json"), r#"{"data_dir": "D:\\Datos"}"#).unwrap();
        assert_eq!(
            logs_dir(home.clone()),
            PathBuf::from("D:\\Datos").join("logs")
        );
        std::fs::write(home.join("location.json"), r#"{"data_dir": null}"#).unwrap();
        assert_eq!(logs_dir(home.clone()), home.join("logs"));
        std::fs::remove_dir_all(&home).unwrap();
    }
}
