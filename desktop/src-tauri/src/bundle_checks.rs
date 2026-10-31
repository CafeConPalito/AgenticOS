//! Checks on the bundle configuration that nothing else would catch before a release build.

#[cfg(test)]
mod tests {
    use std::path::Path;

    fn read(relative: &str) -> String {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(relative);
        std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))
    }

    fn json(relative: &str) -> serde_json::Value {
        serde_json::from_str(&read(relative)).unwrap()
    }

    /// The NSIS template is a copy of Tauri's (phase 21): it must follow the CLI that renders it.
    #[test]
    fn nsis_template_matches_the_tauri_cli() {
        let lock = json("../../package-lock.json");
        let cli = lock["packages"]["node_modules/@tauri-apps/cli"]["version"]
            .as_str()
            .unwrap()
            .to_owned();
        let template = read("windows/installer.nsi");
        assert!(
            template.contains(&format!("@tauri-apps/cli {cli}")),
            "@tauri-apps/cli is {cli}: copy its NSIS template again into windows/installer.nsi"
        );
    }

    #[test]
    fn installer_uses_the_template_and_the_app_icon() {
        let config = json("tauri.conf.json");
        let nsis = &config["bundle"]["windows"]["nsis"];
        assert_eq!(nsis["template"], "windows/installer.nsi");
        assert_eq!(nsis["installerIcon"], "icons/icon.ico");
        assert!(
            read("windows/installer.nsi").contains("MUI_PAGE_CUSTOMFUNCTION_SHOW FinishPageShow")
        );
    }

    /// The avatar cropper shows the picked photo from a `blob:` URL (phase 21: without it the
    /// photo never appeared, only the agent's colour behind it).
    #[test]
    fn csp_lets_the_cropper_show_a_picked_photo() {
        let config = json("tauri.conf.json");
        let csp = config["app"]["security"]["csp"].as_str().unwrap();
        let img = csp
            .split(';')
            .map(str::trim)
            .find(|d| d.starts_with("img-src"))
            .unwrap();
        assert!(img.split_whitespace().any(|s| s == "blob:"), "{img}");
    }
}
