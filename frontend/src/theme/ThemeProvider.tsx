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
  type ResolvedTheme,
  themeSchema,
} from './model'
import { activeThemeId, resolveTheme } from './resolve'

/** The base of the theme on screen: what the `dark:` variants and the toasts follow. */
export type Theme = Base

/** Before phase 20 the choice was only «light» or «dark», kept here. */
export const THEME_STORAGE_KEY = 'agentic-os.theme'
/** The last appearance read or saved, to start with it while the backend answers. */
export const APPEARANCE_STORAGE_KEY = 'agentic-os.appearance'

export const appearanceKey = ['settings', 'appearance'] as const

function isAppearance(value: unknown): value is Appearance {
  if (!value || typeof value !== 'object') return false
  const v = value as Partial<Appearance>
  return (
    (v.mode === 'fixed' || v.mode === 'system') &&
    typeof v.theme === 'string' &&
    typeof v.light_theme === 'string' &&
    typeof v.dark_theme === 'string' &&
    Array.isArray(v.custom) &&
    v.custom.every((theme) => themeSchema.safeParse(theme).success)
  )
}

function readStored(): Appearance {
  try {
    const stored = JSON.parse(localStorage.getItem(APPEARANCE_STORAGE_KEY) ?? 'null') as unknown
    if (isAppearance(stored)) return stored
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

function useSystemDark(): boolean {
  const query = '(prefers-color-scheme: dark)'
  const [dark, setDark] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const media = window.matchMedia(query)
    const onChange = (e: MediaQueryListEvent) => setDark(e.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])
  return dark
}

interface ThemeContextValue {
  /** Base (light or dark) of the theme on screen. */
  theme: Theme
  /** The theme on screen, every value worked out. */
  resolved: ResolvedTheme
  appearance: Appearance
  /** Saves the whole appearance (and paints it at once). */
  setAppearance: (next: Appearance) => void
  /** The light or the dark theme of the appearance, fixed. */
  setTheme: (base: Theme) => void
  toggleTheme: () => void
  /** Shows a theme without saving it (the editor's live preview); null goes back. */
  preview: (theme: ResolvedTheme | null) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  // What this browser last saw: shown while the backend answers, or when it cannot.
  const [stored] = useState<Appearance>(readStored)
  const [previewing, setPreviewing] = useState<ResolvedTheme | null>(null)
  const systemDark = useSystemDark()

  // The backend has the truth; a garbled answer (old backend, offline) is ignored.
  const remote = useQuery({
    queryKey: appearanceKey,
    queryFn: async () => {
      const data = await api.get<unknown>('/api/settings/appearance')
      return isAppearance(data) ? data : null
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
    const untouched =
      remote.mode === 'fixed' && remote.theme === 'navy' && remote.custom.length === 0
    if (legacyLight && untouched) save({ ...remote, theme: 'light' })
  }, [remote, save])

  const chosen = useMemo(
    () => resolveTheme(activeThemeId(appearance, systemDark), appearance.custom),
    [appearance, systemDark],
  )
  const resolved = previewing ?? chosen

  useEffect(() => applyTheme(resolved), [resolved])

  const value = useMemo<ThemeContextValue>(() => {
    const setTheme = (base: Theme) =>
      save({
        ...appearance,
        mode: 'fixed',
        theme: base === 'dark' ? appearance.dark_theme : appearance.light_theme,
      })
    return {
      theme: resolved.base,
      resolved,
      appearance,
      setAppearance: save,
      setTheme,
      toggleTheme: () => setTheme(resolved.base === 'dark' ? 'light' : 'dark'),
      preview: setPreviewing,
    }
  }, [appearance, resolved, save])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider')
  return ctx
}
