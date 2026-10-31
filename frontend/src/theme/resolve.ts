import { BUILTIN_THEMES, type BuiltinTheme } from './builtin'
import { BASE_TOKENS, DEFAULTS, type ResolvedTheme, type ThemeDefinition } from './model'

type AnyTheme = BuiltinTheme | ThemeDefinition

/** Every theme by id: the built-in ones and the person's own. */
export function themeIndex(custom: ThemeDefinition[]): Map<string, AnyTheme> {
  const index = new Map<string, AnyTheme>(BUILTIN_THEMES.map((theme) => [theme.id, theme]))
  for (const theme of custom) index.set(theme.id, theme)
  return index
}

/**
 * All the values of `id`: its base token set, then each theme it extends from the root
 * down, then its own. A theme made from scratch extends none. An unknown id falls back to
 * the navy theme.
 */
export function resolveTheme(id: string, custom: ThemeDefinition[]): ResolvedTheme {
  const index = themeIndex(custom)
  const chain: AnyTheme[] = []
  let current = index.get(id) ?? index.get('navy')!
  const seen = new Set<string>()
  while (!seen.has(current.id)) {
    seen.add(current.id)
    chain.unshift(current)
    const parent = 'extends' in current && current.extends ? index.get(current.extends) : undefined
    if (!parent) break
    current = parent
  }
  const leaf = chain[chain.length - 1]
  const resolved: ResolvedTheme = {
    id: leaf.id,
    base: leaf.base,
    colors: { ...BASE_TOKENS[leaf.base] },
    ...DEFAULTS,
    fontFamily: null,
  }
  for (const theme of chain) {
    Object.assign(resolved.colors, theme.colors)
    // A theme's own font takes over a font of the system it inherited, unless it sets one too.
    if (theme.font) {
      resolved.font = theme.font
      resolved.fontFamily = null
    }
    if ('font_family' in theme && theme.font_family) resolved.fontFamily = theme.font_family
    if (theme.density) resolved.density = theme.density
    if (theme.radius != null) resolved.radius = theme.radius
    if ('scale' in theme && theme.scale != null) resolved.scale = theme.scale
  }
  return resolved
}
