import { Navigate, type RouteObject } from 'react-router'
import { AppShell } from '@/components/layout/AppShell'
import AgentsPage from '@/pages/AgentsPage'
import BoardPage from '@/pages/BoardPage'
import DashboardPage from '@/pages/DashboardPage'
import InboxPage from '@/pages/InboxPage'
import ProjectsPage from '@/pages/ProjectsPage'
import SettingsPage from '@/pages/SettingsPage'
import UsagePage from '@/pages/UsagePage'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'agentes', element: <AgentsPage /> },
      { path: 'proyectos', element: <ProjectsPage /> },
      { path: 'tablero', element: <BoardPage /> },
      { path: 'inbox', element: <InboxPage /> },
      { path: 'consumo', element: <UsagePage /> },
      { path: 'ajustes', element: <SettingsPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]
