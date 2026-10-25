import { useEffect } from 'react'
import { Navigate, type RouteObject } from 'react-router'
import { useDialogs } from '@/stores/dialogs'
import { AppShell } from '@/components/layout/AppShell'
import {
  AgentCrumb,
  type CrumbHandle,
  ProjectCrumb,
  RunCrumb,
  TaskCrumb,
  TextCrumb,
} from '@/components/layout/crumbs'
import AgentEditorPage from '@/pages/agents/AgentEditorPage'
import AgentsPage from '@/pages/agents/AgentsPage'
import BoardPage from '@/pages/BoardPage'
import ClisPage from '@/pages/clis/ClisPage'
import ConnectionsPage from '@/pages/connections/ConnectionsPage'
import HomePage from '@/pages/home/HomePage'
import InboxPage from '@/pages/InboxPage'
import KnowledgePage from '@/pages/knowledge/KnowledgePage'
import ProjectDetailPage from '@/pages/projects/ProjectDetailPage'
import ProjectsPage from '@/pages/projects/ProjectsPage'
import RunPage from '@/pages/runs/RunPage'
import RunsPage from '@/pages/runs/RunsPage'
import SettingsPage from '@/pages/settings/SettingsPage'
import TaskPage from '@/pages/tasks/TaskPage'
import UsagePage from '@/pages/UsagePage'

/** `/agentes/nuevo` and `/proyectos/nuevo` now are dialogs: go to the list and open it. */
function OpenDialog({ dialog, to }: { dialog: 'newAgent' | 'newProject'; to: string }) {
  useEffect(() => {
    const { openNewAgent, openNewProject } = useDialogs.getState()
    if (dialog === 'newAgent') openNewAgent()
    else openNewProject()
  }, [dialog])
  return <Navigate to={to} replace />
}

const crumb = (fn: CrumbHandle['crumb']): CrumbHandle => ({ crumb: fn })

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      {
        path: 'agentes',
        handle: crumb(() => <TextCrumb i18nKey="nav.agents" />),
        children: [
          { index: true, element: <AgentsPage /> },
          // Old links and shortcuts: the list, with the dialog open.
          { path: 'nuevo', element: <OpenDialog dialog="newAgent" to="/agentes" /> },
          { path: ':agentId', element: <Navigate to="resumen" replace /> },
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
          { path: 'nuevo', element: <OpenDialog dialog="newProject" to="/proyectos" /> },
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
      {
        path: 'tablero',
        handle: crumb(() => <TextCrumb i18nKey="nav.board" />),
        children: [
          { index: true, element: <BoardPage /> },
          {
            path: 'tareas/:taskId',
            element: <TaskPage />,
            handle: crumb((params) => <TaskCrumb id={params.taskId} />),
          },
        ],
      },
      {
        path: 'inbox',
        element: <InboxPage />,
        handle: crumb(() => <TextCrumb i18nKey="nav.inbox" />),
      },
      {
        path: 'consumo',
        element: <UsagePage />,
        handle: crumb(() => <TextCrumb i18nKey="nav.usage" />),
      },
      {
        path: 'clis',
        element: <ClisPage />,
        handle: crumb(() => <TextCrumb i18nKey="nav.clis" />),
      },
      {
        path: 'conocimiento',
        element: <KnowledgePage />,
        handle: crumb(() => <TextCrumb i18nKey="nav.knowledge" />),
      },
      {
        path: 'conexiones',
        element: <ConnectionsPage />,
        handle: crumb(() => <TextCrumb i18nKey="nav.connections" />),
      },
      {
        path: 'ajustes',
        element: <SettingsPage />,
        handle: crumb(() => <TextCrumb i18nKey="nav.settings" />),
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]
