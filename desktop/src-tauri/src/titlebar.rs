//! The window's title bar in the theme's colors (phase 20, amendment 1).
//!
//! The bar stays the system's own (buttons where each system puts them, Windows 11's snap
//! layouts); only its colors follow the theme. Windows 11 (build 22000 or later) takes a
//! caption color and a text color; Windows 10 only has a dark or light bar; other systems are
//! left as they are (macOS gets its look from `tauri.macos.conf.json`).

/// What the system can do with the bar.
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum Support {
    /// Windows 11: caption and text colors, and the dark or light mode.
    Colors,
    /// Windows 10: only the dark or light mode.
    DarkOnly,
    None,
}

/// The first Windows build with `DWMWA_CAPTION_COLOR` (Windows 11 21H2).
const WINDOWS_11_BUILD: u32 = 22000;

pub fn support(is_windows: bool, build: u32) -> Support {
    match (is_windows, build) {
        (false, _) => Support::None,
        (true, b) if b >= WINDOWS_11_BUILD => Support::Colors,
        (true, _) => Support::DarkOnly,
    }
}

/// `#rrggbb` as the `0x00BBGGRR` a Windows COLORREF holds.
pub fn colorref(hex: &str) -> Option<u32> {
    let digits = hex.strip_prefix('#')?;
    if digits.len() != 6 || !digits.is_ascii() {
        return None;
    }
    let value = u32::from_str_radix(digits, 16).ok()?;
    let (r, g, b) = ((value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff);
    Some((b << 16) | (g << 8) | r)
}

#[cfg(windows)]
mod native {
    use super::{colorref, support, Support};
    use std::ffi::c_void;

    const DWMWA_USE_IMMERSIVE_DARK_MODE: u32 = 20;
    const DWMWA_CAPTION_COLOR: u32 = 35;
    const DWMWA_TEXT_COLOR: u32 = 36;

    #[repr(C)]
    struct OsVersionInfo {
        size: u32,
        major: u32,
        minor: u32,
        build: u32,
        platform: u32,
        csd: [u16; 128],
    }

    #[link(name = "dwmapi")]
    extern "system" {
        fn DwmSetWindowAttribute(
            hwnd: isize,
            attribute: u32,
            value: *const c_void,
            size: u32,
        ) -> i32;
    }

    #[link(name = "ntdll")]
    extern "system" {
        fn RtlGetVersion(info: *mut OsVersionInfo) -> i32;
    }

    fn build_number() -> u32 {
        let mut info = OsVersionInfo {
            size: std::mem::size_of::<OsVersionInfo>() as u32,
            major: 0,
            minor: 0,
            build: 0,
            platform: 0,
            csd: [0; 128],
        };
        // SAFETY: `info` is a valid OSVERSIONINFOW with its size set.
        if unsafe { RtlGetVersion(&mut info) } == 0 {
            info.build
        } else {
            0
        }
    }

    fn set(hwnd: isize, attribute: u32, value: u32) {
        // SAFETY: a 4-byte value for a 4-byte DWM attribute; a failure only means no change.
        unsafe {
            DwmSetWindowAttribute(
                hwnd,
                attribute,
                (&value as *const u32).cast(),
                std::mem::size_of::<u32>() as u32,
            );
        }
    }

    pub fn apply(hwnd: isize, background: &str, foreground: &str, dark: bool) {
        let support = support(true, build_number());
        set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, u32::from(dark));
        if support == Support::Colors {
            if let Some(color) = colorref(background) {
                set(hwnd, DWMWA_CAPTION_COLOR, color);
            }
            if let Some(color) = colorref(foreground) {
                set(hwnd, DWMWA_TEXT_COLOR, color);
            }
        }
    }
}

/// Paints the title bar of the window with the theme's colors (`#rrggbb`) and base.
#[tauri::command]
pub fn set_titlebar(
    window: tauri::WebviewWindow,
    background: String,
    foreground: String,
    dark: bool,
) {
    #[cfg(windows)]
    if let Ok(hwnd) = window.hwnd() {
        native::apply(hwnd.0 as isize, &background, &foreground, dark);
    }
    #[cfg(not(windows))]
    {
        let _ = (window, background, foreground, dark);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn colorref_swaps_red_and_blue() {
        assert_eq!(colorref("#0f2347"), Some(0x0047_230f));
        assert_eq!(colorref("#ffffff"), Some(0x00ff_ffff));
        assert_eq!(colorref("#000000"), Some(0));
    }

    #[test]
    fn colorref_rejects_what_is_not_a_hex_color() {
        for bad in ["0f2347", "#fff", "#12345g", "#12345678", "", "#ééé"] {
            assert_eq!(colorref(bad), None, "{bad}");
        }
    }

    #[test]
    fn support_depends_on_the_system_and_the_build() {
        assert_eq!(support(true, 22621), Support::Colors);
        assert_eq!(support(true, 22000), Support::Colors);
        assert_eq!(support(true, 19045), Support::DarkOnly);
        assert_eq!(support(false, 22621), Support::None);
    }
}
