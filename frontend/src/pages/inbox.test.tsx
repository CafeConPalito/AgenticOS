import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeInboxItem, makeRun, makeTask } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

const notify = vi.hoisted(() => vi.fn(async () => true))
vi.mock('@/lib/notify', () => ({
  notify,
  notificationPermission: async () => 'granted',
  askNotificationPermission: async () => 'granted',
}))

describe('Inbox', () => {
  beforeEach(() => notify.mockClear())

  it('answers a question with an option and approves a command', async () => {
    const question = makeInboxItem({
      kind: 'question',
      title: '¿Postgres o SQLite?',
      options: ['Postgres', 'SQLite'],
      notified_at: '2026-10-11T10:00:00Z',
    })
    const approval = makeInboxItem({
      kind: 'approval',
      title: '¿Puedo continuar?',
      command: 'Bash: npm install -D @playwright/test',
      run_id: 'run-1',
      notified_at: '2026-10-11T10:00:00Z',
    })
    const backend = createFakeBackend({ inbox: [question, approval] })
    const user = userEvent.setup()
    renderApp('/inbox')

    const card = await screen.findByRole('article', {
      name: `${es.inbox.kinds.question}: ¿Postgres o SQLite?`,
    })
    await user.click(within(card).getByRole('button', { name: 'SQLite' }))
    await user.click(within(card).getByRole('button', { name: es.inbox.answer }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/inbox/${question.id}/answer`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/inbox/${question.id}/answer`)[0].body).toEqual({
      text: 'SQLite',
    })

    const command = screen.getByRole('article', {
      name: `${es.inbox.kinds.approval}: ${es.inbox.approvalTitle}`,
    })
    expect(within(command).getByText(/npm install -D @playwright\/test/)).toBeVisible()
    await user.click(within(command).getByRole('button', { name: es.inbox.approve }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/inbox/${approval.id}/approve`)).toHaveLength(1),
    )

    await user.click(screen.getByRole('tab', { name: new RegExp(es.inbox.resolved) }))
    expect(await screen.findByText(es.inbox.resolution.approved)).toBeVisible()
    expect(screen.getByText('Respondido: «SQLite»')).toBeVisible()
  })

  it('notifies each new item once', async () => {
    const fresh = makeInboxItem({ kind: 'blocker', title: 'Me falta la clave de Stripe' })
    const delivery = makeInboxItem({ kind: 'delivery', title: 'T-3 · Guía de estilo' })
    const backend = createFakeBackend({ inbox: [fresh, delivery] })
    renderApp('/')

    await waitFor(() => expect(notify).toHaveBeenCalledTimes(1))
    // Deliveries do not notify by default; both are marked so no window notifies them again.
    expect(notify).toHaveBeenCalledWith(
      `${es.inbox.kinds.blocker} · Dev · Tienda online`,
      'Me falta la clave de Stripe',
      expect.objectContaining({ sound: true }),
    )
    await waitFor(() =>
      expect(backend.calls.filter((c) => c.path.endsWith('/notified'))).toHaveLength(2),
    )
  })

  it('offers to resume an interrupted task from its «Atención» item', async () => {
    const task = makeTask({ status: 'waiting_human', waiting_reason: 'interrupted' })
    const run = makeRun({ task_id: task.id, status: 'interrupted', resumable: true })
    task.last_run_id = run.id
    const item = makeInboxItem({ kind: 'attention', task_id: task.id, title: 'T-1 · Login' })
    const backend = createFakeBackend({ tasks: [task], runs: [run], inbox: [item] })
    const user = userEvent.setup()
    renderApp('/inbox')

    await user.click(await screen.findByRole('button', { name: es.runs.resume.button }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/runs/${run.id}/resume`)).toHaveLength(1),
    )
  })

  it('settings switch a kind off', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')
    const review = await screen.findByRole('switch', {
      name: new RegExp(es.settings.notifications.review),
    })
    await waitFor(() => expect(review).toBeEnabled())
    await user.click(review)
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/notifications')).toHaveLength(1),
    )
    expect(backend.callsTo('PUT', '/api/settings/notifications')[0].body).toMatchObject({
      review: false,
      approval: true,
    })
  })
})

describe('Task page tree and subtasks', () => {
  it('lists the execution tree and switches the terminal to a subagent', async () => {
    const task = makeTask({
      status: 'running',
      active_run_id: 'run-main',
      subtasks_total: 1,
      subtasks_done: 0,
    })
    const sub = makeTask({
      title: 'Documentar la API',
      parent_task_id: task.id,
      agent_name: 'Rita',
    })
    createFakeBackend({
      tasks: [task, sub],
      trees: {
        [task.id]: [
          {
            kind: 'run',
            id: 'run-main',
            label: 'Dev',
            color: '#4FD1C5',
            stage_name: 'Desarrollo',
            status: 'running',
            started_at: '2026-10-11T10:00:00Z',
            ended_at: null,
            children: [
              {
                kind: 'run',
                id: 'run-child',
                label: 'Ayudante',
                color: '#B5E061',
                stage_name: null,
                status: 'completed',
                started_at: '2026-10-11T10:01:00Z',
                ended_at: '2026-10-11T10:03:00Z',
                children: [],
              },
              {
                kind: 'native',
                id: 'toolu_1',
                label: 'Contar archivos',
                color: null,
                stage_name: null,
                status: 'done',
                started_at: '2026-10-11T10:01:00Z',
                ended_at: '2026-10-11T10:02:00Z',
                children: [],
              },
            ],
          },
        ],
      },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    const tree = await screen.findByRole('region', { name: es.tasks.detail.tree })
    expect(within(tree).getByText('Contar archivos')).toBeVisible()
    const child = within(tree).getByRole('button', { name: /Ayudante/ })
    expect(child).toHaveAttribute('aria-pressed', 'false')
    await user.click(child)
    expect(child).toHaveAttribute('aria-pressed', 'true')

    expect(await screen.findByText('Subtareas · 0/1')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Documentar la API' })).toBeVisible()
    expect(screen.getByText('@Rita')).toBeVisible()
  })
})
