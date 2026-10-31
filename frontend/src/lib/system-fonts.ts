import { invoke, isTauri } from '@tauri-apps/api/core'
import { useQuery } from '@tanstack/react-query'

/** `queryLocalFonts` (Local Font Access): Chromium only, behind a permission prompt. */
type FontQuery = () => Promise<{ family: string }[]>

/**
 * The font families installed on the system (phase 22, ADR 0028): from the desktop shell, or
 * from the browser's Local Font Access where there is one (it asks for permission). Null when
 * there is no way to know: the person types the name.
 */
export async function listSystemFonts(): Promise<string[] | null> {
  if (isTauri()) return invoke<string[]>('system_fonts')
  const query = (window as unknown as { queryLocalFonts?: FontQuery }).queryLocalFonts
  if (!query) return null
  try {
    const families = new Set((await query()).map((font) => font.family))
    return [...families].sort((a, b) => a.localeCompare(b, 'es', { sensitivity: 'base' }))
  } catch {
    return null // permission refused
  }
}

const SAMPLE = 'mmmmmmmmmmlli WQ@#0123 Agentic OS'
const FALLBACKS = ['monospace', 'serif'] as const

/**
 * Whether the webview paints `family` by its name. With an unknown name the text falls back
 * to the generic family after it, so its width matches that one with both fallbacks. Variable
 * fonts with named instances are listed by a name the webview does not take (spike S1). True
 * when it cannot be measured.
 */
export function paintsByName(family: string): boolean {
  const context = document.createElement('canvas').getContext('2d')
  if (!context) return true
  const width = (font: string) => {
    context.font = `32px ${font}`
    return context.measureText(SAMPLE).width
  }
  return FALLBACKS.some((generic) => width(`"${family}", ${generic}`) !== width(generic))
}

/** The fonts of the system the webview can paint, once per session; null when unknown. */
export function useSystemFonts(enabled = true) {
  return useQuery({
    queryKey: ['system-fonts'],
    queryFn: async () => (await listSystemFonts())?.filter(paintsByName) ?? null,
    enabled,
    staleTime: Infinity,
    retry: false,
  })
}

/** Whether a theme's font is missing here: not in the list, or not painted when no list. */
export function isFontMissing(family: string, installed: string[] | null | undefined): boolean {
  if (installed) return !installed.some((name) => name.toLowerCase() === family.toLowerCase())
  return !paintsByName(family)
}
