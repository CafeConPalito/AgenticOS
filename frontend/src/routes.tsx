import { Navigate, type RouteObject } from 'react-router'
import { AppShell } from '@/components/layout/AppShell'
import {
  AgentCrumb,
  type CrumbHandle,
  ProjectCrumb,
  RunCrumb,
  TextCrumb,
} from '@/components/layout/crumbs'
import AgentEditorPage from '@/pages/agents/AgentEditorPage'
import AgentsPage from '@/pages/agents/AgentsPage'
import NewAgentPage from '@/pages/agents/NewAgentPage'
import BoardPage from '@/pages/BoardPage'
import DashboardPage from '@/pages/DashboardPage'
import InboxPage from '@/pages/InboxPage'
import NewProjectPage from '@/pages/projects/NewProjectPage'
import ProjectDetailPage from '@/pages/projects/ProjectDetailPage'
import ProjectsPage from '@/pages/projects/ProjectsPage'
import RunPage from '@/pages/runs/RunPage'
import RunsPage from '@/pages/runs/RunsPage'
import SettingsPage from '@/pages/SettingsPage'
import UsagePage from '@/pages/UsagePage'

const crumb = (fn: CrumbHandle['crumb']): CrumbHandle => ({ crumb: fn })

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      {
        path: 'agentes',
        handle: crumb(() => <TextCrumb i18nKey="nav.agents" />),
        children: [
          { index: true, element: <AgentsPage /> },
          {
            path: 'nuevo',
            element: <NewAgentPage />,
            handle: crumb(() => <TextCrumb i18nKey="agents.new.title" />),
          },
          { path: ':agentId', element: <Navigate to="general" replace /> },
          {
            path: ':agentId/:tab',
            element: <AgentEditorPage />,
            handle: crumb((params) => <AgentCrumb id={params.agentId} />),
          },
        ],
      },
      {
        path: 'proyectos',
        handle: crumb(() => <TextCrumb i18nKey="nav.projects" />),
        children: [
          { index: true, element: <ProjectsPage /> },
          {
            path: 'nuevo',
            element: <NewProjectPage />,
            handle: crumb(() => <TextCrumb i18nKey="projects.new.title" />),
          },
          { path: ':projectId', element: <Navigate to="summary" replace /> },
          {
            path: ':projectId/:tab',
            element: <ProjectDetailPage />,
            handle: crumb((params) => <ProjectCrumb id={params.projectId} />),
          },
        ],
      },
      {
        path: 'ejecuciones',
        handle: crumb(() => <TextCrumb i18nKey="nav.runs" />),
        children: [
          { index: true, element: <RunsPage /> },
          {
            path: ':runId',
            element: <RunPage />,
            handle: crumb((params) => <RunCrumb id={params.runId} />),
          },
        ],
      },
      { path: 'tablero', element: <BoardPage /> },
      { path: 'inbox', element: <InboxPage /> },
      { path: 'consumo', element: <UsagePage /> },
      { path: 'ajustes', element: <SettingsPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]
