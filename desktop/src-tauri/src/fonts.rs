//! The fonts installed on the system (phase 22, ADR 0028), for a theme to use one. WebView2
//! gives no list without a permission prompt, so it is read here with `fontdb`, which looks in
//! the system's font folders and in the user's own (spike S1).

use std::collections::BTreeSet;
use std::sync::OnceLock;

static FAMILIES: OnceLock<Vec<String>> = OnceLock::new();

/// The font families of the system, sorted, each once. Read the first time it is asked
/// (under a second, cold) off the main thread, then kept: a font installed later shows up
/// after a restart.
#[tauri::command]
pub async fn system_fonts() -> Result<Vec<String>, String> {
    if let Some(families) = FAMILIES.get() {
        return Ok(families.clone());
    }
    let families = tauri::async_runtime::spawn_blocking(|| {
        let mut db = fontdb::Database::new();
        db.load_system_fonts();
        families(
            db.faces()
                .filter_map(|face| face.families.first().map(|(name, _)| name.as_str())),
        )
    })
    .await
    .map_err(|e| e.to_string())?;
    Ok(FAMILIES.get_or_init(|| families).clone())
}

/// Each family once, sorted without regard to case, leaving out the hidden ones (their name
/// starts with `@` for vertical text or `.` for the system's own).
fn families<'a>(names: impl Iterator<Item = &'a str>) -> Vec<String> {
    let unique: BTreeSet<(String, &str)> = names
        .map(str::trim)
        .filter(|name| !name.is_empty() && !name.starts_with(['@', '.']))
        .map(|name| (name.to_lowercase(), name))
        .collect();
    let mut out: Vec<String> = Vec::with_capacity(unique.len());
    for (_, name) in unique {
        if out
            .last()
            .is_none_or(|last| !last.eq_ignore_ascii_case(name))
        {
            out.push(name.to_string());
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::families;

    #[test]
    fn each_family_once_sorted_without_the_hidden_ones() {
        let names = [
            "Segoe UI",
            "Arial",
            "segoe UI",
            "@MS Gothic",
            ".SF NS",
            " ",
            "Cascadia Code",
            "Arial",
        ];
        assert_eq!(
            families(names.into_iter()),
            ["Arial", "Cascadia Code", "Segoe UI"]
        );
    }
}
