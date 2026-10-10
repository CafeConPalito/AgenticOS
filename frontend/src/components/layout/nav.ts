import {
  Bot,
  ChartColumn,
  FolderGit2,
  Inbox,
  LayoutDashboard,
  Settings,
  SquareKanban,
  SquareTerminal,
  type LucideIcon,
} from 'lucide-react'

export type Section =
  'dashboard' | 'agents' | 'projects' | 'runs' | 'board' | 'inbox' | 'usage' | 'settings'

export type PrimaryAction = 'newTask' | 'newAgent' | 'newProject' | 'launchRun' | 'exportCsv'

export interface NavItem {
  id: Section
  path: string
  icon: LucideIcon
  primary?: PrimaryAction
}

export const NAV: NavItem[] = [
  { id: 'dashboard', path: '/', icon: LayoutDashboard, primary: 'newTask' },
  { id: 'agents', path: '/agentes', icon: Bot, primary: 'newAgent' },
  { id: 'projects', path: '/proyectos', icon: FolderGit2, primary: 'newProject' },
  { id: 'runs', path: '/ejecuciones', icon: SquareTerminal, primary: 'launchRun' },
  { id: 'board', path: '/tablero', icon: SquareKanban, primary: 'newTask' },
  { id: 'inbox', path: '/inbox', icon: Inbox },
  { id: 'usage', path: '/consumo', icon: ChartColumn, primary: 'exportCsv' },
  { id: 'settings', path: '/ajustes', icon: Settings },
]

export function sectionForPath(pathname: string): NavItem {
  return (
    NAV.find((item) => item.path !== '/' && pathname.startsWith(item.path)) ??
    NAV.find((item) => item.path === pathname) ??
    NAV[0]
  )
}
