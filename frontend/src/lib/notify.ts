import { isTauri } from '@tauri-apps/api/core'
import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from '@tauri-apps/plugin-notification'

/**
 * System notifications: native Windows toasts in the desktop app (Tauri plugin), the browser's
 * Notification API in development. The backend is a windowless sidecar, so the UI shows them.
 */
export type NotifyPermission = 'granted' | 'denied' | 'default' | 'unsupported'

export async function notificationPermission(): Promise<NotifyPermission> {
  if (isTauri()) return (await isPermissionGranted()) ? 'granted' : 'default'
  if (typeof Notification === 'undefined') return 'unsupported'
  return Notification.permission
}

export async function askNotificationPermission(): Promise<NotifyPermission> {
  if (isTauri()) return (await requestPermission()) === 'granted' ? 'granted' : 'denied'
  if (typeof Notification === 'undefined') return 'unsupported'
  return Notification.requestPermission()
}

export async function notify(
  title: string,
  body: string,
  options: { sound: boolean; onClick?: () => void },
): Promise<boolean> {
  if (isTauri()) {
    if (!(await isPermissionGranted())) return false
    // Windows: clicking the toast brings the app to the front (the Inbox shows the item).
    sendNotification({ title, body, ...(options.sound ? { sound: 'Default' } : {}) })
    return true
  }
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return false
  const notification = new Notification(title, { body, silent: !options.sound })
  notification.onclick = () => {
    window.focus()
    options.onClick?.()
    notification.close()
  }
  return true
}
