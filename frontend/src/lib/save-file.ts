import { invoke, isTauri } from '@tauri-apps/api/core'
import { toast } from 'sonner'
import i18n from '@/i18n'

export interface SaveRequest {
  /** Suggested file name, e.g. `Redactor.agent.json`. */
  name: string
  text: string
  /** MIME type for the browser download. */
  type: string
  /** The save dialog's filter: its label and extensions without the dot. */
  filter: string
  extensions: string[]
}

/**
 * Saves a text file the user exports (phase 21). In the desktop app WebView2 ignores
 * `<a download>`, so «Guardar como» is opened by the shell, which writes the file: the path, or
 * null when cancelled. In the browser it is a download: undefined.
 */
export async function saveFile(request: SaveRequest): Promise<string | null | undefined> {
  if (isTauri()) {
    return invoke<string | null>('save_file', {
      name: request.name,
      contents: request.text,
      filter: request.filter,
      extensions: request.extensions,
    })
  }
  const url = URL.createObjectURL(new Blob([request.text], { type: request.type }))
  const link = document.createElement('a')
  link.href = url
  link.download = request.name
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Later than the click: some browsers read the URL after the event has returned.
  setTimeout(() => URL.revokeObjectURL(url), 0)
  return undefined
}

/** The notice after an export: where it went, or that it was downloaded. Nothing if cancelled. */
export function toastSaved(result: string | null | undefined) {
  if (result === null) return
  toast.success(
    result === undefined ? i18n.t('common.downloaded') : i18n.t('common.savedAt', { path: result }),
  )
}
