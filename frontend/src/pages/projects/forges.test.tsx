import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { PullDetail, PullRequest } from '@/api/forges'
import es from '@/i18n/es.json'
import {
  type FakeRepoGit,
  createFakeBackend,
  makeBranch,
  makeProject,
  makeRepo,
} from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

vi.mock('@/lib/notify', () => ({
  notify: vi.fn(async () => true),
  notificationPermission: async () => 'granted',
  askNotificationPermission: async () => 'granted',
}))

function pull(overrides: Partial<PullRequest> = {}): PullRequest {
  return {
    number: 7,
    title: 'T-1: Login',
    state: 'open',
    draft: false,
    author: 'ana',
    head: 'agentic/T-1',
    base: 'main',
    url: 'https://github.com/ana/shop/pull/7',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    mergeable: true,
    ...overrides,
  }
}

function detail(overrides: Partial<PullDetail> = {}): PullDetail {
  return {
    ...pull(),
    body: 'Añade el login',
    checks: [
      { name: 'tests', state: 'success', url: '' },
      { name: 'lint', state: 'failure', url: '' },
    ],
    checks_state: 'failure',
    reviews: [{ author: 'luis', state: 'approved' }],
    comments: [{ author: 'luis', body: 'Muy bien', created_at: null }],
    ...overrides,
  }
}

function setup(git: FakeRepoGit = {}) {
  const project = makeProject()
  const repo = makeRepo({ id: 'r1', project_id: project.id, name: 'web' })
  const backend = createFakeBackend({
    projects: [project],
    repos: { [project.id]: [repo] },
    git: {
      r1: {
        ...git,
        branches: git.branches ?? [makeBranch({ name: 'main', current: true })],
        status: { branch: 'main', ...git.status },
      },
    },
  })
  installFakeWebSocket()
  return { project, backend }
}

function open(projectId: string) {
  renderApp(`/proyectos/${projectId}/git?section=pulls`)
}

describe('Pull requests section', () => {
  it('lists them with their state and shows the detail with checks, reviews and comments', async () => {
    const { project } = setup({
      pulls: [pull(), pull({ number: 8, title: 'Otro', draft: true })],
      pullDetails: { 7: detail() },
    })
    const user = userEvent.setup()
    open(project.id)

    expect(await screen.findByText('T-1: Login')).toBeVisible()
    expect(screen.getByText(es.git.pulls.draft)).toBeVisible()
    await user.click(screen.getByRole('button', { name: /T-1: Login/ }))

    const panel = await screen.findByRole('region', { name: 'Pull request 7' })
    expect(within(panel).getByText('Añade el login')).toBeVisible()
    expect(within(panel).getByText('tests')).toBeVisible()
    expect(within(panel).getByText(es.git.pulls.checkState.failure)).toBeVisible()
    expect(within(panel).getByText(/luis · aprobó/)).toBeVisible()
    expect(within(panel).getByText('Muy bien')).toBeVisible()
  })

  it('merges with the chosen method after confirming', async () => {
    const { project, backend } = setup({ pulls: [pull()], pullDetails: { 7: detail() } })
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByRole('button', { name: /T-1: Login/ }))
    const panel = await screen.findByRole('region', { name: 'Pull request 7' })
    await user.selectOptions(
      within(panel).getByRole('combobox', { name: es.git.pulls.method }),
      'squash',
    )
    await user.click(within(panel).getByRole('button', { name: es.git.pulls.merge }))
    expect(backend.callsTo('POST', '/api/repos/r1/pulls/7/merge')).toHaveLength(0)
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: es.git.pulls.merge }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/pulls/7/merge')[0].body).toEqual({
        method: 'squash',
      }),
    )
  })

  it('closes, updates the branch and reopens', async () => {
    const { project, backend } = setup({
      pulls: [pull(), pull({ number: 8, state: 'closed', title: 'Cerrado' })],
      pullDetails: { 7: detail(), 8: detail({ number: 8, state: 'closed', title: 'Cerrado' }) },
    })
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByRole('button', { name: /T-1: Login/ }))
    const panel = await screen.findByRole('region', { name: 'Pull request 7' })
    await user.click(within(panel).getByRole('button', { name: es.git.pulls.updateBranch }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/pulls/7/update-branch')).toHaveLength(1),
    )
    await user.click(within(panel).getByRole('button', { name: es.git.pulls.close }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/pulls/7/close')).toHaveLength(1),
    )

    await user.click(screen.getByRole('button', { name: es.git.pulls.filters.all }))
    await user.click(await screen.findByRole('button', { name: /^#8/ }))
    const closed = await screen.findByRole('region', { name: 'Pull request 8' })
    await user.click(within(closed).getByRole('button', { name: es.git.pulls.reopen }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/pulls/8/reopen')).toHaveLength(1),
    )
  })

  it('creates one from a branch', async () => {
    const { project, backend } = setup({
      branches: [makeBranch({ name: 'main', current: true }), makeBranch({ name: 'agentic/T-1' })],
    })
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByRole('button', { name: es.git.pulls.create }))
    const form = await screen.findByRole('form', { name: es.git.pulls.create })
    await user.selectOptions(within(form).getByLabelText(es.git.pulls.head), 'agentic/T-1')
    await user.type(within(form).getByLabelText(es.git.pulls.title), 'T-1: Login')
    await user.click(within(form).getByRole('checkbox', { name: es.git.pulls.asDraft }))
    await user.click(within(form).getByRole('button', { name: es.git.pulls.submit }))

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/pulls')[0].body).toEqual({
        title: 'T-1: Login',
        body: '',
        head: 'agentic/T-1',
        base: 'main',
        draft: true,
      }),
    )
  })

  it('explains an unknown host and a missing token, and saves a pasted token', async () => {
    const { project } = setup({
      forge: { kind: null, host: 'git.empresa.es', remote: 'origin', has_token: false },
    })
    open(project.id)
    expect(await screen.findByText(es.git.pulls.noForgeTitle)).toBeVisible()
  })

  it('asks for a token when git has none', async () => {
    const { project, backend } = setup({
      forge: { kind: 'github', host: 'github.com', remote: 'origin', has_token: false },
    })
    const user = userEvent.setup()
    open(project.id)

    expect(await screen.findByText(/Git no tiene ningún token para github.com/)).toBeVisible()
    await user.type(screen.getByLabelText(es.git.pulls.token), 'ghp_x')
    await user.click(screen.getByRole('button', { name: es.git.pulls.saveToken }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/git/forge-token')[0].body).toEqual({
        host: 'github.com',
        token: 'ghp_x',
      }),
    )
  })
})

describe('Repository forge setting', () => {
  it('lets the person say which service a self-hosted remote is', async () => {
    const project = makeProject()
    const repo = makeRepo({ id: 'r1', project_id: project.id, name: 'web' })
    const backend = createFakeBackend({ projects: [project], repos: { [project.id]: [repo] } })
    installFakeWebSocket()
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/settings`)

    await user.selectOptions(
      await screen.findByRole('combobox', { name: `${es.projects.repos.forge} web` }),
      'gitlab',
    )
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/repos/r1')[0].body).toEqual({ forge: 'gitlab' }),
    )
  })
})
