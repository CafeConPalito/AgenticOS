//! The desktop shell's own log (phase 20, ADR 0027): `<data>/logs/desktop.log`, next to the
//! backend's. It records the sidecar's lifecycle (start, ready, exit, restart, give up) and,
//! when the sidecar dies, the last lines it wrote to stderr. It also builds the logs bundle
//! when the backend is down (the backend builds a fuller one when it is up).

use std::collections::VecDeque;
use std::fs::{self, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

use regex::Regex;

use crate::sidecar;

/// Rotated at start when bigger than this.
const MAX_BYTES: u64 = 1024 * 1024;
/// Lines of the sidecar's stderr kept in memory, written only if it dies.
const STDERR_LINES: usize = 40;
/// What of each log goes into the bundle (the newest lines).
const BUNDLE_BACKEND_BYTES: u64 = 10 * 1024 * 1024;
const BUNDLE_DESKTOP_BYTES: u64 = 2 * 1024 * 1024;
const HIDDEN: &str = "«oculto»";

static STDERR: Mutex<VecDeque<String>> = Mutex::new(VecDeque::new());

pub fn path() -> PathBuf {
    sidecar::logs_dir(sidecar::home_dir()).join("desktop.log")
}

/// At start: a log over MAX_BYTES becomes `desktop.log.1` (replacing the previous one).
pub fn rotate() {
    let current = path();
    if fs::metadata(&current).is_ok_and(|m| m.len() > MAX_BYTES) {
        let _ = fs::rename(&current, current.with_extension("log.1"));
    }
}

/// One line, with the UTC time. Failing to write the log never stops the app.
pub fn write(line: &str) {
    let file = path();
    if let Some(folder) = file.parent() {
        let _ = fs::create_dir_all(folder);
    }
    if let Ok(mut out) = OpenOptions::new().create(true).append(true).open(file) {
        let _ = writeln!(out, "{} {}", timestamp(SystemTime::now()), line.trim_end());
    }
}

/// A stderr line of the sidecar: only kept in memory.
pub fn stderr_line(line: &str) {
    let mut lines = STDERR.lock().unwrap();
    if lines.len() == STDERR_LINES {
        lines.pop_front();
    }
    lines.push_back(line.trim_end().to_string());
}

fn user_home() -> Option<PathBuf> {
    std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
}

/// The sidecar died: write what it said last.
pub fn dump_stderr() {
    let lines: Vec<String> = STDERR.lock().unwrap().drain(..).collect();
    if lines.is_empty() {
        return;
    }
    write(&format!(
        "last {} stderr lines of the backend:",
        lines.len()
    ));
    for line in lines {
        write(&format!("  | {}", redact(&line, user_home().as_deref())));
    }
}

/// `2026-10-28T09:00:00Z` without a date crate (days to civil date, Howard Hinnant's method).
pub fn timestamp(at: SystemTime) -> String {
    let secs = at
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0) as i64;
    let (days, rest) = (secs.div_euclid(86_400), secs.rem_euclid(86_400));
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        rest / 3600,
        rest % 3600 / 60,
        rest % 60
    )
}

fn patterns() -> &'static [(Regex, &'static str)] {
    static PATTERNS: OnceLock<Vec<(Regex, &'static str)>> = OnceLock::new();
    PATTERNS.get_or_init(|| {
        let keys = r"api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|id[_-]?token|token|secret|client[_-]?secret|password|passwd|pwd|auth|authorization|code|state|session|sig|signature|credential|credentials|private[_-]?key|email";
        // In `key=value` text the generic words (state, code, session…) are left alone.
        let assign = r"api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|id[_-]?token|token|secret|client[_-]?secret|password|passwd|pwd|authorization|credential|credentials|private[_-]?key|email";
        // The same as the backend's services/redact.py (the bundle without the backend).
        [
            (r#"(/[ra]/)[A-Za-z0-9_\-]{8,}"#.to_string(), "${1}«oculto»"),
            (
                r#"(?i)\b((?:set-)?cookie["']?\s*[:=]\s*["']?)[^\r\n"']+"#.to_string(),
                "${1}«oculto»",
            ),
            (
                r#"(?i)\b(proxy-authorization|authorization|x-api-key)(["']?\s*[:=]\s*["']?)(?:(?:bearer|basic|token)\s+)?[^\s"',;]+"#.to_string(),
                "${1}${2}«oculto»",
            ),
            (format!(r#"(?i)([?&](?:{keys})=)[^&\s#"']+"#), "${1}«oculto»"),
            (
                format!(r#"(?i)(["']?(?:{assign})["']?\s*[:=]\s*["']?)[^\s"',;&}}«]{{4,}}"#),
                "${1}«oculto»",
            ),
            (
                r"\b(?:sk-(?:ant-)?[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9\-]{10,}|AIza[0-9A-Za-z_\-]{35}|glpat-[A-Za-z0-9_\-]{20,}|hf_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,})".to_string(),
                HIDDEN,
            ),
            (r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b".to_string(), "«correo»"),
            (
                r#"(?i)\b([a-z]:[\\/]+users[\\/]+|/home/|/users/)[^\\/\s"']+"#.to_string(),
                "${1}<usuario>",
            ),
        ]
        .into_iter()
        .map(|(pattern, replacement)| (Regex::new(&pattern).expect("valid pattern"), replacement))
        .collect()
    })
}

/// Hides secrets, e-mail addresses and the user's name in paths.
pub fn redact(line: &str, home: Option<&Path>) -> String {
    let mut text = line.to_string();
    if let Some(home) = home.map(|h| h.to_string_lossy().to_string()) {
        if let Some(parent) = Path::new(&home).parent() {
            let hidden = parent.join("<usuario>").to_string_lossy().to_string();
            text = text.replace(&home, &hidden);
        }
    }
    for (pattern, replacement) in patterns() {
        text = pattern.replace_all(&text, *replacement).into_owned();
    }
    text
}

fn tail(path: &Path, max: u64) -> Option<String> {
    let mut file = fs::File::open(path).ok()?;
    let size = file.metadata().ok()?.len();
    file.seek(SeekFrom::Start(size.saturating_sub(max))).ok()?;
    let mut data = Vec::new();
    file.read_to_end(&mut data).ok()?;
    let text = String::from_utf8_lossy(&data).into_owned();
    // From the first whole line when the file was cut.
    Some(match (size > max, text.find('\n')) {
        (true, Some(cut)) => text[cut + 1..].to_string(),
        _ => text,
    })
}

/// The bundle without the backend: its log and this one, redacted, written at `target`.
pub fn bundle(folder: &Path, target: &Path, home: Option<&Path>) -> Result<Vec<String>, String> {
    use zip::write::SimpleFileOptions;

    let mut names = Vec::new();
    let partial = target.with_extension("zip.part");
    {
        let file = fs::File::create(&partial).map_err(|e| e.to_string())?;
        let mut archive = zip::ZipWriter::new(file);
        let options =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, max) in [
            ("backend.log", BUNDLE_BACKEND_BYTES),
            ("desktop.log", BUNDLE_DESKTOP_BYTES),
        ] {
            let Some(text) = tail(&folder.join(name), max) else {
                continue;
            };
            let clean: Vec<String> = text.lines().map(|l| redact(l, home)).collect();
            archive
                .start_file(format!("logs/{name}"), options)
                .map_err(|e| e.to_string())?;
            archive
                .write_all(clean.join("\n").as_bytes())
                .map_err(|e| e.to_string())?;
            names.push(format!("logs/{name}"));
        }
        let info = format!(
            "Agentic OS {} (app de escritorio)\nGenerado sin backend: {}\nSistema: {} {}\n\n\
             Solo los registros del backend y de la app de escritorio, con los secretos, los \
             correos y el nombre de usuario ocultos. Sin salidas de terminal ni contenido.\n",
            env!("CARGO_PKG_VERSION"),
            timestamp(SystemTime::now()),
            std::env::consts::OS,
            std::env::consts::ARCH,
        );
        archive
            .start_file("info.txt", options)
            .map_err(|e| e.to_string())?;
        archive
            .write_all(info.as_bytes())
            .map_err(|e| e.to_string())?;
        names.push("info.txt".into());
        archive.finish().map_err(|e| e.to_string())?;
    }
    fs::rename(&partial, target).map_err(|e| e.to_string())?;
    Ok(names)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn formats_utc_time() {
        let at = UNIX_EPOCH + Duration::from_secs(1_793_178_000); // 2026-10-28T09:00:00Z
        assert_eq!(timestamp(at), "2026-10-28T09:00:00Z");
        assert_eq!(timestamp(UNIX_EPOCH), "1970-01-01T00:00:00Z");
    }

    #[test]
    fn hides_secrets_emails_and_the_user() {
        let home = Path::new(r"C:\Users\albano");
        let line = r#"GET /r/Zx9kq3LmN0pQrStU/mcp?api_key=sk-LEAK1234 Authorization: Bearer abc.def from someone@example.com in C:\Users\albano\AppData"#;
        let clean = redact(line, Some(home));
        for leak in [
            "Zx9kq3LmN0pQrStU",
            "LEAK1234",
            "abc.def",
            "someone@example.com",
            "albano",
        ] {
            assert!(!clean.contains(leak), "{leak} in {clean}");
        }
        assert!(clean.contains("/r/«oculto»/mcp"));
        assert!(clean.contains(r"C:\Users\<usuario>\AppData"));
        assert_eq!(
            redact("run_started agent=Dev page=2", None),
            "run_started agent=Dev page=2"
        );
    }

    #[test]
    fn bundles_both_logs_redacted() {
        let folder = std::env::temp_dir().join(format!("agentic-desklog-{}", std::process::id()));
        fs::create_dir_all(&folder).unwrap();
        fs::write(
            folder.join("backend.log"),
            "ok\ntoken=ghp_abcdefghijklmnopqrstuvwxyz0123\n",
        )
        .unwrap();
        fs::write(folder.join("desktop.log"), "sidecar ready port=4321\n").unwrap();
        let target = folder.join("out.zip");
        let names = bundle(&folder, &target, None).unwrap();
        assert_eq!(names, ["logs/backend.log", "logs/desktop.log", "info.txt"]);
        let mut archive = zip::ZipArchive::new(fs::File::open(&target).unwrap()).unwrap();
        let mut backend = String::new();
        archive
            .by_name("logs/backend.log")
            .unwrap()
            .read_to_string(&mut backend)
            .unwrap();
        assert!(backend.contains("ok") && !backend.contains("ghp_abcdef"));
        assert!(!target.with_extension("zip.part").exists());
        fs::remove_dir_all(&folder).unwrap();
    }
}
