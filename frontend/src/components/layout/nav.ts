export type TopSection = 'board' | 'runs' | 'settings'
/** Second-level pages: reachable by route, Ctrl+K and the breadcrumb, not from the top bar. */
export type SecondarySection = 'agents' | 'projects' | 'inbox' | 'usage'
export type Section = 'home' | TopSection | SecondarySection

export interface NavItem {
  id: Section
  path: string
}

/** The top navigation, in order. Inicio is the logo. */
export const TOP_NAV: (NavItem & { id: TopSection })[] = [
  { id: 'board', path: '/tablero' },
  { id: 'runs', path: '/ejecuciones' },
  { id: 'settings', path: '/ajustes' },
]

export const SECONDARY_NAV: (NavItem & { id: SecondarySection })[] = [
  { id: 'agents', path: '/agentes' },
  { id: 'projects', path: '/proyectos' },
  { id: 'inbox', path: '/inbox' },
  { id: 'usage', path: '/consumo' },
]

export const HOME: NavItem = { id: 'home', path: '/' }

export function sectionForPath(pathname: string): NavItem {
  return [...TOP_NAV, ...SECONDARY_NAV].find((item) => pathname.startsWith(item.path)) ?? HOME
}
