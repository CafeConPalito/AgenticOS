import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import {
  createFakeBackend,
  makeAgent,
  makeChanges,
  makeFileChange,
  makeInboxItem,
  makeProject,
  makeRun,
  makeTask,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'

vi.mock('@/lib/notify', () => ({
  notify: vi.fn(async () => true),
  notificationPermission: async () => 'granted',
  askNotificationPermission: async () => 'granted',
}))

const TWO_FILES = makeChanges({
  files: [
    makeFileChange({ path: 'api.py', additions: 2 }),
    makeFileChange({ path: 'ui.py', additions: 1, deletions: 1 }),
  ],
})

describe('Changes in a review and a delivery', () => {
  it('opens the diff from the review and decides from the panel', async () => {
    const task = makeTask({ title: 'Login', status: 'review' })
    const item = makeInboxItem({
      kind: 'review',
      title: 'T-1 · Login',
      task_id: task.id,
      task_code: task.code,
      changes: { files: 2, additions: 3, deletions: 1 },
    })
    const backend = createFakeBackend({
      tasks: [task],
      inbox: [item],
      changes: { [`task:${task.id}`]: { summary: TWO_FILES } },
    })
    const user = userEvent.setup()
    renderApp('/inbox')

    const card = await screen.findByRole('article', {
      name: `${es.inbox.kinds.review}: T-1 · Login`,
    })
    const open = within(card).getByRole('button', { name: /Ver cambios/ })
    expect(open).toHaveTextContent('2 ficheros')
    expect(open).toHaveTextContent('+3')
    await user.click(open)

    const panel = await screen.findByRole('dialog', { name: `Cambios de ${task.code}` })
    const list = await within(panel).findByRole('list', { name: es.changes.fileList })
    expect(within(list).getByText('api.py')).toBeVisible()
    // The same actions sit at the foot of the panel.
    await user.click(within(panel).getByRole('button', { name: es.inbox.reviewApprove }))

    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/inbox/${item.id}/review`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/inbox/${item.id}/review`)[0].body).toMatchObject({
      approve: true,
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('rejects with a reason from the panel', async () => {
    const task = makeTask({ title: 'Login', status: 'review' })
    const item = makeInboxItem({
      kind: 'review',
      title: 'T-1 · Login',
      task_id: task.id,
      task_code: task.code,
      changes: { files: 2, additions: 3, deletions: 1 },
    })
    const backend = createFakeBackend({
      tasks: [task],
      inbox: [item],
      changes: { [`task:${task.id}`]: { summary: TWO_FILES } },
    })
    const user = userEvent.setup()
    renderApp('/inbox')

    await user.click(await screen.findByRole('button', { name: /Ver cambios/ }))
    const panel = await screen.findByRole('dialog')
    await user.click(within(panel).getByRole('button', { name: es.inbox.reviewReject }))
    await user.type(within(panel).getByLabelText(es.inbox.reasonPlaceholder), 'Falta el test')
    await user.click(within(panel).getByRole('button', { name: es.inbox.reviewReject }))

    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/inbox/${item.id}/review`)[0]?.body).toMatchObject({
        approve: false,
        reason: 'Falta el test',
      }),
    )
  })

  it('shows the diff of a delivery and marks it as seen from the panel', async () => {
    const task = makeTask({ title: 'Guía de estilo', status: 'done' })
    const item = makeInboxItem({
      kind: 'delivery',
      title: 'T-3 · Guía de estilo',
      task_id: task.id,
      task_code: task.code,
      changes: { files: 2, additions: 3, deletions: 1 },
    })
    const backend = createFakeBackend({
      tasks: [task],
      inbox: [item],
      changes: { [`task:${task.id}`]: { summary: TWO_FILES } },
    })
    const user = userEvent.setup()
    renderApp('/inbox')

    await user.click(await screen.findByRole('button', { name: /Ver cambios/ }))
    const panel = await screen.findByRole('dialog')
    await user.click(within(panel).getByRole('button', { name: es.inbox.markReviewed }))

    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/inbox/${item.id}/dismiss`)).toHaveLength(1),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('has no «Ver cambios» in the other kinds of request', async () => {
    const task = makeTask()
    createFakeBackend({
      tasks: [task],
      inbox: [makeInboxItem({ kind: 'attention', title: 'T-1 · Falló', task_id: task.id })],
    })
    renderApp('/inbox')

    await screen.findByText('T-1 · Falló')
    expect(screen.queryByRole('button', { name: /Ver cambios/ })).toBeNull()
  })
})

describe('Changes tab of an agent', () => {
  it('lists the runs that changed code, filters by project and opens a diff', async () => {
    const dev = makeAgent({ name: 'Dev' })
    const web = makeProject({ name: 'Web' })
    const blog = makeProject({ name: 'Blog' })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [web, blog],
      agentChanges: [
        {
          run_id: 'run-a',
          project_id: web.id,
          project_name: 'Web',
          task_id: 't-1',
          task_code: 'T-1',
          task_title: 'Login',
          started_at: '2026-10-15T10:00:00Z',
          created_at: '2026-10-15T10:00:00Z',
          totals: { files: 2, additions: 3, deletions: 1 },
        },
        {
          run_id: 'run-b',
          project_id: blog.id,
          project_name: 'Blog',
          task_id: null,
          task_code: null,
          task_title: null,
          started_at: null,
          created_at: '2026-10-14T10:00:00Z',
          totals: { files: 1, additions: 7, deletions: 0 },
        },
      ],
      changes: { 'run:run-a': { summary: TWO_FILES } },
    })
    const user = userEvent.setup()
    renderApp(`/agentes/${dev.id}/changes`)

    const login = await screen.findByRole('button', {
      name: 'Ver los cambios de «T-1 · Login»',
    })
    expect(login).toHaveTextContent('+3')
    expect(
      screen.getByRole('button', { name: `Ver los cambios de «${es.changes.agent.manual}»` }),
    ).toBeVisible()

    await user.click(screen.getByRole('combobox', { name: es.changes.agent.project }))
    await user.click(await screen.findByRole('option', { name: 'Blog' }))
    await waitFor(() => expect(screen.queryByText(/T-1 · Login/)).toBeNull())
    expect(backend.calls.some((c) => c.query.includes(`project_id=${blog.id}`))).toBe(true)

    await user.click(screen.getByRole('combobox', { name: es.changes.agent.project }))
    await user.click(await screen.findByRole('option', { name: es.changes.agent.allProjects }))
    await user.click(await screen.findByRole('button', { name: /T-1 · Login/ }))

    const panel = await screen.findByRole('dialog', { name: es.changes.titleRun })
    const files = await within(panel).findByRole('list', { name: es.changes.fileList })
    expect(within(files).getByText('ui.py')).toBeVisible()
  })

  it('says so when the agent has not changed code yet', async () => {
    const dev = makeAgent({ name: 'Dev' })
    createFakeBackend({ agents: [dev] })
    renderApp(`/agentes/${dev.id}/changes`)

    expect(await screen.findByText(es.changes.agent.empty)).toBeVisible()
  })
})

describe('Changes on the runs and the task pages', () => {
  it('adds a «Cambios» column to the runs list', async () => {
    const withChanges = makeRun({
      prompt: 'Arregla el login',
      changes: { files: 2, additions: 5, deletions: 1 },
    })
    const without = makeRun({ prompt: 'Explica el repo', changes: null })
    createFakeBackend({ runs: [withChanges, without] })
    renderApp('/ejecuciones')

    const row = await screen.findByRole('row', { name: new RegExp('Arregla el login') })
    expect(within(row).getByText('+5')).toBeVisible()
    expect(within(row).getByText('−1')).toBeVisible()
    expect(screen.getByRole('columnheader', { name: es.runs.columns.changes })).toBeVisible()
    const other = screen.getByRole('row', { name: new RegExp('Explica el repo') })
    expect(within(other).queryByText(/^\+/)).toBeNull()
  })

  it('opens the run diff from the run page, and hides the entry without a diff', async () => {
    const run = makeRun({ status: 'completed' })
    const plain = makeRun({ status: 'completed', prompt: 'Sin git' })
    createFakeBackend({
      runs: [run, plain],
      changes: { [`run:${run.id}`]: { summary: TWO_FILES } },
    })
    const user = userEvent.setup()
    const { unmount } = renderApp(`/ejecuciones/${run.id}`)

    await user.click(await screen.findByRole('button', { name: /Ver cambios/ }))
    const panel = await screen.findByRole('dialog', { name: es.changes.titleRun })
    const files = await within(panel).findByRole('list', { name: es.changes.fileList })
    expect(within(files).getByText('api.py')).toBeVisible()
    unmount()

    renderApp(`/ejecuciones/${plain.id}`)
    await screen.findAllByText('Sin git')
    expect(screen.queryByRole('button', { name: /Ver cambios/ })).toBeNull()
  })

  it('opens the task diff from the task page', async () => {
    const task = makeTask({ title: 'Login', status: 'done' })
    createFakeBackend({
      tasks: [task],
      changes: { [`task:${task.id}`]: { summary: TWO_FILES } },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    await user.click(await screen.findByRole('button', { name: /Ver cambios/ }))
    const panel = await screen.findByRole('dialog', { name: `Cambios de ${task.code}` })
    expect(await within(panel).findByText('2 ficheros')).toBeVisible()
  })
})

describe('Settings · Limpieza · instantáneas', () => {
  it('lists the snapshots per project and deletes them after confirming', async () => {
    const backend = createFakeBackend({
      snapshots: [{ project_id: 'project-1', project_name: 'Web', runs: 3 }],
    })
    const user = userEvent.setup()
    renderApp('/ajustes')

    const list = await screen.findByRole('list', { name: es.settings.cleanup.snapshots })
    expect(within(list).getByText('3 ejecuciones')).toBeVisible()
    await user.click(
      within(list).getByRole('button', {
        name: `${es.settings.cleanup.deleteSnapshots} Web`,
      }),
    )
    const confirm = await screen.findByRole('alertdialog')
    expect(backend.callsTo('POST', '/api/maintenance/snapshots/project-1/delete')).toHaveLength(0)
    await user.click(
      within(confirm).getByRole('button', { name: es.settings.cleanup.deleteSnapshots }),
    )

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/maintenance/snapshots/project-1/delete')).toHaveLength(
        1,
      ),
    )
    expect(await screen.findByText(es.settings.cleanup.noSnapshots)).toBeVisible()
  })
})
