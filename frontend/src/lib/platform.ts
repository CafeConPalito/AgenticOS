import { isTauri } from '@tauri-apps/api/core'

/** Whether the desktop app runs on macOS, where the header doubles as the title bar. */
export function isMacDesktop(): boolean {
  return isTauri() && /Macintosh|Mac OS X/i.test(navigator.userAgent)
}
