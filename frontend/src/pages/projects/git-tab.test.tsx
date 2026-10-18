import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { FileDiff } from '@/api/changes'
import type { JobState } from '@/api/git'
import es from '@/i18n/es.json'
import { installFakeWebSocket } from '@/test/fake-socket'
import {
  createFakeBackend,
  diffLine,
  makeBranch,
  makeCommit,
  makeFileChange,
  makeProject,
  makeRepo,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { useGitJobs } from '@/stores/git-jobs'

vi.mock('@/lib/notify', () => ({
  notify: vi.fn(async () => true),
  notificationPermission: async () => 'granted',
  askNotificationPermission: async () => 'granted',
}))

const DIFF: FileDiff = {
  path: 'api.py',
  binary: false,
  too_large: false,
  hunks: [
    {
      old_start: 1,
      old_lines: 2,
      new_start: 1,
      new_lines: 3,
      header: '',
      lines: [
        diffLine('context', 'uno', 1, 1),
        diffLine('del', 'dos', 2, null),
        diffLine('add', 'DOS', null, 2),
        diffLine('add', 'tres', null, 3),
      ],
    },
  ],
}

const API = makeFileChange({ path: 'api.py', status: 'modified', additions: 2, deletions: 1 })
const NEW = makeFileChange({ path: 'nuevo.py', status: 'added', additions: 4 })

function setup(extra: Parameters<typeof createFakeBackend>[0] = {}) {
  const project = makeProject()
  const repo = makeRepo({ id: 'r1', project_id: project.id, name: 'web' })
  const backend = createFakeBackend({
    projects: [project],
    repos: { [project.id]: [repo] },
    git: {
      r1: {
        status: { branch: 'main', upstream: 'origin/main', ahead: 2, behind: 1 },
        unstaged: [API, NEW],
        diffs: { 'api.py': DIFF },
        branches: [
          makeBranch({ name: 'main', current: true, upstream: 'origin/main' }),
          makeBranch({
            name: 'agentic/T-3',
            task_id: 't3',
            task_code: 'T-3',
            task_title: 'Login',
            task_status: 'review',
            base_ahead: 2,
            base_behind: 0,
          }),
          makeBranch({ name: 'otra', integrated: true, base_ahead: 0, base_behind: 1 }),
        ],
        commits: [
          makeCommit({ subject: 'feat: login', sha: 'c'.repeat(40) }),
          makeCommit({ subject: 'init', sha: 'd'.repeat(40) }),
        ],
      },
    },
    ...extra,
  })
  return { project, backend }
}

function open(projectId: string) {
  const sockets = installFakeWebSocket()
  renderApp(`/proyectos/${projectId}/git`)
  return sockets
}

describe('Git tab', () => {
  it('shows the branch, how far it is from its remote and the changes of the repository', async () => {
    const { project } = setup()
    open(project.id)

    expect(await screen.findByRole('combobox', { name: es.git.branch })).toHaveValue('main')
    expect(screen.getByLabelText(es.git.ahead)).toHaveTextContent('2')
    expect(screen.getByLabelText(es.git.behind)).toHaveTextContent('1')
    const unstaged = await screen.findByRole('region', { name: es.git.changes.unstaged })
    expect(within(unstaged).getByText('api.py')).toBeVisible()
    expect(within(unstaged).getByText('nuevo.py')).toBeVisible()
    expect(screen.getByText(es.git.changes.noStaged)).toBeVisible()
    // The number of changes next to «Cambios».
    expect(screen.getByRole('button', { name: /Cambios/ })).toHaveTextContent('2')
  })

  it('stages a file and shows it among the staged ones', async () => {
    const { project, backend } = setup()
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByRole('button', { name: `${es.git.changes.stage} api.py` }))

    const staged = await screen.findByRole('region', { name: es.git.changes.staged })
    expect(await within(staged).findByText('api.py')).toBeVisible()
    expect(backend.callsTo('POST', '/api/repos/r1/stage')[0].body).toEqual({ paths: ['api.py'] })
    await user.click(screen.getByRole('button', { name: `${es.git.changes.unstage} api.py` }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/unstage')[0].body).toEqual({
        paths: ['api.py'],
      }),
    )
  })

  it('picks lines in the diff and stages only those', async () => {
    const { project, backend } = setup()
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByTitle('api.py'))
    const file = await screen.findByRole('region', { name: 'api.py' })
    expect(await within(file).findByText('DOS')).toBeVisible()
    const stageLines = screen.getByRole('button', { name: es.git.changes.stageLines })
    expect(stageLines).toBeDisabled()

    await user.click(
      within(file).getByLabelText(`${es.changes.pickAdded.replace('{{number}}', '3')}`),
    )
    expect(screen.getByText('1 línea elegida')).toBeVisible()
    await user.click(stageLines)

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/apply')[0].body).toMatchObject({
        action: 'stage',
        path: 'api.py',
        lines: [{ kind: 'add', no: 3 }],
      }),
    )
  })

  it('picking a whole hunk picks every changed line in it', async () => {
    const { project } = setup()
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByTitle('api.py'))
    const file = await screen.findByRole('region', { name: 'api.py' })
    await user.click(await within(file).findByLabelText(/Elegir el bloque/))

    expect(screen.getByText('3 líneas elegidas')).toBeVisible()
  })

  it('asks before discarding and says what is lost', async () => {
    const { project, backend } = setup()
    const user = userEvent.setup()
    open(project.id)

    await user.click(
      await screen.findByRole('button', { name: `${es.git.changes.discard} nuevo.py` }),
    )
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText(/1 fichero/)).toBeVisible()
    expect(backend.callsTo('POST', '/api/repos/r1/discard')).toHaveLength(0)

    await user.click(within(dialog).getByRole('button', { name: es.git.changes.discardConfirm }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/discard')[0].body).toEqual({
        paths: ['nuevo.py'],
        confirm: true,
      }),
    )
  })

  it('shows who changed each line of the file picked', async () => {
    const { project } = setup({
      git: {
        r1: {
          unstaged: [API],
          diffs: { 'api.py': DIFF },
          blame: [
            {
              start: 1,
              lines: 2,
              sha: 'e'.repeat(40),
              short: 'eeeeeee',
              author: 'Ana',
              date: new Date().toISOString(),
              summary: 'feat: login',
              text: ['uno', 'dos'],
              agent_name: 'Dev',
              task_code: 'T-3',
            },
          ],
        },
      },
    })
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByTitle('api.py'))
    await user.click(await screen.findByRole('button', { name: es.git.blame.open }))

    const group = await screen.findByRole('region', { name: 'eeeeeee 1' })
    expect(within(group).getByText('feat: login')).toBeVisible()
    expect(within(group).getByText('Dev')).toBeVisible() // the agent that made the commit
    expect(within(group).getByText('uno')).toBeVisible()
  })

  it('commits what is staged with a summary and a description', async () => {
    const { project, backend } = setup()
    const user = userEvent.setup()
    open(project.id)
    await user.click(await screen.findByRole('button', { name: `${es.git.changes.stage} api.py` }))
    await screen.findByRole('button', { name: `${es.git.changes.unstage} api.py` })

    const commit = screen.getByRole('button', { name: 'Commit de 1 fichero' })
    expect(commit).toBeDisabled() // no summary yet
    await user.type(screen.getByLabelText(es.git.changes.summary), 'feat: login')
    await user.type(screen.getByLabelText(es.git.changes.body), 'con detalle')
    await user.click(commit)

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/commit')[0].body).toEqual({
        message: 'feat: login\n\ncon detalle',
        amend: false,
        no_verify: false,
      }),
    )
    expect(await screen.findByText(/Commit .* hecho/)).toBeVisible()
  })

  it('lists the commits and shows the changes of the one picked', async () => {
    const { project } = setup()
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByRole('button', { name: es.git.section.history }))
    const commits = await screen.findByRole('list', { name: es.git.history.commits })
    expect(within(commits).getByText('feat: login')).toBeVisible()
    expect(screen.getByText(es.git.history.pick)).toBeVisible()

    await user.click(within(commits).getByText('feat: login'))
    expect(await screen.findByRole('heading', { name: 'feat: login' })).toBeVisible()
    expect((await screen.findAllByText('api.py')).length).toBeGreaterThan(0) // its changed file
  })

  it('shows the task of a task branch and filters the branches', async () => {
    const { project } = setup()
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByRole('button', { name: es.git.section.branches }))
    expect(await screen.findByRole('link', { name: /T-3 · Login/ })).toHaveAttribute(
      'href',
      '/tablero/tareas/t3',
    )
    const list = () => screen.getByRole('link', { name: /T-3/ }).closest('ul')!
    expect(within(list()).getByText('main')).toBeVisible()
    expect(within(list()).getByText('otra')).toBeVisible()

    await user.click(screen.getByRole('button', { name: es.git.branches.filters.tasks }))
    expect(within(list()).queryByText('otra')).not.toBeInTheDocument()
    expect(within(list()).getByRole('link', { name: /T-3/ })).toBeVisible()

    await user.click(screen.getByRole('button', { name: es.git.branches.filters.open }))
    expect(within(list()).queryByText('otra')).not.toBeInTheDocument() // integrated
    expect(within(list()).queryByText('main')).not.toBeInTheDocument() // the current one
  })

  it('creates a branch and switches to it', async () => {
    const { project, backend } = setup()
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByRole('button', { name: es.git.section.branches }))
    await user.type(await screen.findByLabelText(es.git.branches.newName), 'feature/x')
    await user.click(screen.getByRole('button', { name: es.git.branches.create }))

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/branches')[0].body).toEqual({
        name: 'feature/x',
        switch: true,
      }),
    )
  })

  it('fetch starts a job whose progress arrives by events, and it can be cancelled', async () => {
    const { project, backend } = setup()
    const user = userEvent.setup()
    const sockets = open(project.id)

    await user.click(await screen.findByRole('button', { name: es.git.fetch }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/repos/r1/fetch')).toHaveLength(1))
    const job = await screen.findByRole('progressbar', {}, { timeout: 200 }).catch(() => null)
    expect(job).toBeNull() // no percentage yet

    const socket = sockets.instances.find((s) => s.url.endsWith('/api/git/events'))!
    const started = Object.values(useGitJobs.getState().jobs)[0]
    const running: JobState = {
      id: started.id,
      repo_id: 'r1',
      kind: 'fetch',
      status: 'running',
      phase: 'Receiving objects',
      percent: 45,
      message: '',
      error_code: null,
      started_at: new Date().toISOString(),
      ended_at: null,
    }
    act(() => {
      socket.open()
      socket.onmessage?.({ data: JSON.stringify({ type: 'job', job: running }) })
    })

    const bar = await screen.findByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '45')
    expect(screen.getByText('Receiving objects')).toBeVisible()
    await user.click(screen.getByRole('button', { name: es.git.jobs.cancel }))
    await waitFor(() =>
      expect(backend.callsTo('DELETE', `/api/git/jobs/${started.id}`)).toHaveLength(1),
    )

    act(() => {
      socket.onmessage?.({
        data: JSON.stringify({
          type: 'job',
          job: { ...running, status: 'failed', error_code: 'network', message: 'sin red' },
        }),
      })
    })
    expect(await screen.findByText(es.git.errors.network)).toBeVisible()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('reads the repository again when the backend says it changed', async () => {
    const { project, backend } = setup()
    const sockets = open(project.id)
    await screen.findByRole('combobox', { name: es.git.branch })
    const before = backend.callsTo('GET', '/api/repos/r1/status').length
    const socket = sockets.instances.find((s) => s.url.endsWith('/api/git/events'))!

    act(() => {
      socket.open()
      socket.onmessage?.({ data: JSON.stringify({ type: 'repo_changed', repo_id: 'r1' }) })
    })

    await waitFor(() =>
      expect(backend.callsTo('GET', '/api/repos/r1/status').length).toBeGreaterThan(before),
    )
  })

  it('a project with no repositories says so and points to the settings', async () => {
    const project = makeProject()
    createFakeBackend({ projects: [project], repos: { [project.id]: [] } })
    open(project.id)

    expect(await screen.findByText(es.git.none.title)).toBeVisible()
    expect(screen.getByRole('link', { name: es.git.none.action })).toHaveAttribute(
      'href',
      `/proyectos/${project.id}/settings`,
    )
  })
})

describe('Git tab with several repositories', () => {
  function several() {
    const project = makeProject()
    const backend = createFakeBackend({
      projects: [project],
      repos: {
        [project.id]: [
          makeRepo({ id: 'a', project_id: project.id, name: 'backend', rel_path: 'backend' }),
          makeRepo({ id: 'b', project_id: project.id, name: 'frontend', rel_path: 'frontend' }),
        ],
      },
      git: {
        a: { status: { branch: 'main' }, unstaged: [API], diffs: { 'api.py': DIFF } },
        b: { status: { branch: 'develop', upstream: 'origin/develop', ahead: 1 }, unstaged: [] },
      },
    })
    return { project, backend }
  }

  it('lists every repository with its state and opens the one picked', async () => {
    const { project } = several()
    const user = userEvent.setup()
    open(project.id)

    const aside = await screen.findByRole('complementary', { name: es.git.repositories })
    expect(within(aside).getByText('backend')).toBeVisible()
    expect(within(aside).getByText('develop')).toBeVisible()
    expect(within(aside).getByText('1 cambio')).toBeVisible()
    expect(within(aside).getByText(es.git.overview.clean)).toBeVisible()

    expect(await screen.findByRole('heading', { name: 'backend' })).toBeVisible()
    await user.click(within(aside).getByText('frontend'))
    expect(await screen.findByRole('heading', { name: 'frontend' })).toBeVisible()
    expect(screen.getByRole('combobox', { name: es.git.branch })).toBeInTheDocument()
  })

  it('applies an action to the repositories that are ticked, or to all of them', async () => {
    const { project, backend } = several()
    const user = userEvent.setup()
    open(project.id)
    const group = await screen.findByRole('group', { name: es.git.batch.title })

    await user.click(within(group).getByRole('button', { name: es.git.batch.fetch }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/projects/${project.id}/git/batch`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/projects/${project.id}/git/batch`)[0].body).toEqual({
      action: 'fetch',
      repo_ids: ['a', 'b'],
    })

    await user.click(screen.getByLabelText(`${es.git.batch.tick} frontend`))
    expect(within(group).getByText('1 repositorio elegido')).toBeVisible()
    await user.click(within(group).getByRole('button', { name: es.git.batch.create_branch }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByRole('textbox'), 'release')
    await user.click(within(dialog).getByRole('button', { name: es.git.batch.run }))

    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/projects/${project.id}/git/batch`)).toHaveLength(2),
    )
    expect(backend.callsTo('POST', `/api/projects/${project.id}/git/batch`)[1].body).toEqual({
      action: 'create_branch',
      repo_ids: ['b'],
      name: 'release',
    })
  })
})
