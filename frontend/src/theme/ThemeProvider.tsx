import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'
import { applyTheme } from './apply'
import {
  type Appearance,
  type Base,
  DEFAULT_APPEARANCE,
  type LegacyFollow,
  type ResolvedTheme,
  themeSchema,
} from './model'
import { resolveTheme } from './resolve'

/** The base of the theme on screen: what the `dark:` variants and the toasts follow. */
export type Theme = Base

/** Before phase 20 the choice was only «light» or «dark», kept here. */
export const THEME_STORAGE_KEY = 'agentic-os.theme'
/** The last appearance read or saved, to start with it while the backend answers. */
export const APPEARANCE_STORAGE_KEY = 'agentic-os.appearance'

export const appearanceKey = ['settings', 'appearance'] as const

const systemDark = () => window.matchMedia('(prefers-color-scheme: dark)').matches

/**
 * An appearance document, or null if it is not one. One of phase 20 that followed the system
 * (`mode` in this browser's copy, `legacy_follow` from the backend) becomes the theme that
 * was on screen (ADR 0028); `legacy` says it still has to be saved that way.
 */
function readAppearance(value: unknown): { appearance: Appearance; legacy: boolean } | null {
  if (!value || typeof value !== 'object') return null
  const v = value as Partial<Appearance> &
    Partial<LegacyFollow> & {
      mode?: string
      legacy_follow?: LegacyFollow | null
    }
  if (
    typeof v.theme !== 'string' ||
    !Array.isArray(v.custom) ||
    !v.custom.every((theme) => themeSchema.safeParse(theme).success)
  )
    return null
  const follow =
    v.legacy_follow ??
    (v.mode === 'system' && v.light_theme && v.dark_theme
      ? { light_theme: v.light_theme, dark_theme: v.dark_theme }
      : null)
  const theme = follow ? (systemDark() ? follow.dark_theme : follow.light_theme) : v.theme
  return { appearance: { theme, custom: v.custom }, legacy: follow !== null }
}

function readStored(): Appearance {
  try {
    const stored = readAppearance(
      JSON.parse(localStorage.getItem(APPEARANCE_STORAGE_KEY) ?? 'null') as unknown,
    )
    if (stored) return stored.appearance
    if (localStorage.getItem(THEME_STORAGE_KEY) === 'light')
      return { ...DEFAULT_APPEARANCE, theme: 'light' }
  } catch {
    // Storage unavailable or broken: the defaults.
  }
  return DEFAULT_APPEARANCE
}

function store(appearance: Appearance) {
  try {
    localStorage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(appearance))
  } catch {
    // Storage unavailable: the backend still has it.
  }
}

interface ThemeContextValue {
  /** Base (light or dark) of the theme on screen. */
  theme: Theme
  /** The theme on screen, every value worked out. */
  resolved: ResolvedTheme
  appearance: Appearance
  /** Saves the whole appearance (and paints it at once). */
  setAppearance: (next: Appearance) => void
  /** Shows a theme without saving it (the editor's live preview); null goes back. */
  preview: (theme: ResolvedTheme | null) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  // What this browser last saw: shown while the backend answers, or when it cannot.
  const [stored] = useState<Appearance>(readStored)
  const [previewing, setPreviewing] = useState<ResolvedTheme | null>(null)

  // The backend has the truth; a garbled answer (old backend, offline) is ignored.
  const remote = useQuery({
    queryKey: appearanceKey,
    queryFn: async () => {
      const read = readAppearance(await api.get<unknown>('/api/settings/appearance'))
      // A phase 20 document that followed the system: saved now with the theme on screen.
      if (read?.legacy) await api.put('/api/settings/appearance', read.appearance)
      return read?.appearance ?? null
    },
    staleTime: Infinity,
  }).data
  const appearance = remote ?? stored

  const save = useCallback(
    (next: Appearance) => {
      // Optimistic: painted at once; a refusal puts back what the backend has.
      queryClient.setQueryData(appearanceKey, next)
      api.put<Appearance>('/api/settings/appearance', next).catch((error: unknown) => {
        toast.error(errorMessage(error))
        void queryClient.invalidateQueries({ queryKey: appearanceKey })
      })
    },
    [queryClient],
  )

  useEffect(() => store(appearance), [appearance])

  // Carry over the light theme chosen before phase 20 (it lived only in this browser).
  useEffect(() => {
    if (!remote) return
    let legacyLight = false
    try {
      legacyLight = localStorage.getItem(THEME_STORAGE_KEY) === 'light'
      localStorage.removeItem(THEME_STORAGE_KEY)
    } catch {
      // Nothing to carry over.
    }
    const untouched = remote.theme === 'navy' && remote.custom.length === 0
    if (legacyLight && untouched) save({ ...remote, theme: 'light' })
  }, [remote, save])

  const chosen = useMemo(() => resolveTheme(appearance.theme, appearance.custom), [appearance])
  const resolved = previewing ?? chosen

  useEffect(() => applyTheme(resolved), [resolved])

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme: resolved.base,
      resolved,
      appearance,
      setAppearance: save,
      preview: setPreviewing,
    }),
    [appearance, resolved, save],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider')
  return ctx
}
