import { isTauri } from '@tauri-apps/api/core'

/** Native «choose files» dialog (desktop app only; the browser cannot give real paths). */
export async function pickFiles(title: string, multiple = true): Promise<string[]> {
  const { open } = await import('@tauri-apps/plugin-dialog')
  const selected = await open({ multiple, directory: false, title })
  if (selected === null) return []
  return Array.isArray(selected) ? selected : [selected]
}

/**
 * Files dropped on the window (desktop app only): the paths, so the library keeps references
 * and no copies. `onHover` tells when something is being dragged over. Returns the stop function.
 */
export async function listenForDroppedFiles(
  onDrop: (paths: string[]) => void,
  onHover: (hovering: boolean) => void,
): Promise<() => void> {
  if (!isTauri()) return () => {}
  const { getCurrentWebview } = await import('@tauri-apps/api/webview')
  return getCurrentWebview().onDragDropEvent((event) => {
    const payload = event.payload
    if (payload.type === 'enter' || payload.type === 'over') onHover(true)
    else if (payload.type === 'drop') {
      onHover(false)
      if (payload.paths.length > 0) onDrop(payload.paths)
    } else onHover(false)
  })
}
