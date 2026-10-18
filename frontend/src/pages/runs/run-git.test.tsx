import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { RunRepoGit } from '@/api/run-git'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makeProject, makeRun } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

vi.mock('@xterm/xterm', () => import('@/test/fake-xterm'))
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() {}
  },
}))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))
vi.mock('@/lib/notify', () => ({
  notify: vi.fn(async () => true),
  notificationPermission: async () => 'granted',
  askNotificationPermission: async () => 'granted',
}))

function activity(overrides: Partial<NonNullable<RunRepoGit['activity']>> = {}) {
  return {
    commits: [
      { sha: 'a'.repeat(40), subject: 'feat login', kind: 'commit' as const },
      { sha: 'b'.repeat(40), subject: 'feat login, reworded', kind: 'amend' as const },
    ],
    branches: [
      { name: 'agentic/T-1', start: 'c'.repeat(40), end: 'b'.repeat(40) },
      { name: 'lateral', start: null, end: 'b'.repeat(40) },
    ],
    tags: [{ name: 'hito', start: null, end: 'b'.repeat(40) }],
    pushes: [
      { remote: 'origin', branch: 'agentic/T-1', start: null, end: 'b'.repeat(40), forced: false },
    ],
    head_start: 'branch:main',
    head_end: 'branch:main',
    undone: false,
    ...overrides,
  }
}

function setup(rows: RunRepoGit[], extra: Parameters<typeof createFakeBackend>[0] = {}) {
  const project = makeProject()
  const agent = makeAgent({ name: 'Dev' })
  const run = makeRun({ project_id: project.id, agent_id: agent.id, status: 'exited' })
  const backend = createFakeBackend({
    projects: [project],
    agents: [agent],
    runs: [run],
    runGit: { [run.id]: rows },
    ...extra,
  })
  return { run, backend }
}

function row(overrides: Partial<RunRepoGit> = {}): RunRepoGit {
  return {
    repo_id: 'r1',
    name: 'web',
    path: 'D:\\web',
    activity: activity(),
    can_undo: true,
    pushed: true,
    ...overrides,
  }
}

async function section(runId: string) {
  renderApp(`/ejecuciones/${runId}`)
  return within(await screen.findByRole('region', { name: es.runs.git.title }))
}

describe('Git section of a run', () => {
  it('shows the commits, branches, tags and pushes the run made', async () => {
    const { run } = setup([row()])
    const git = await section(run.id)

    const commits = git.getByRole('list', { name: 'Commits de web' })
    expect(within(commits).getByText('feat login')).toBeVisible()
    expect(within(commits).getByText(es.runs.git.kind.amend)).toBeVisible()
    const branches = git.getByRole('list', { name: 'Ramas de web' })
    expect(within(branches).getByText('lateral')).toBeVisible()
    expect(within(branches).getByText(es.runs.git.created)).toBeVisible()
    expect(within(branches).getByText(es.runs.git.moved)).toBeVisible()
    expect(git.getByText('hito')).toBeVisible()
    expect(
      within(git.getByRole('list', { name: 'Pushes de web' })).getByText('origin/agentic/T-1'),
    ).toBeVisible()
  })

  it('marks a forced push', async () => {
    const forced = activity({
      pushes: [
        {
          remote: 'origin',
          branch: 'main',
          start: 'a'.repeat(40),
          end: 'b'.repeat(40),
          forced: true,
        },
      ],
    })
    const { run } = setup([row({ activity: forced })])
    const git = await section(run.id)
    expect(git.getByText(es.runs.git.forced)).toBeVisible()
  })

  it('undoes after confirming, and says that what was pushed stays', async () => {
    const { run, backend } = setup([row()], {
      undoReport: {
        repos: {
          r1: {
            operation_id: 'op-1',
            items: [
              { branch: 'agentic/T-1', result: 'reverted', reason: null },
              { branch: 'lateral', result: 'deleted', reason: null },
            ],
          },
        },
      },
    })
    const user = userEvent.setup()
    const git = await section(run.id)

    await user.click(git.getByRole('button', { name: es.runs.git.undo }))
    expect(backend.callsTo('POST', `/api/runs/${run.id}/git/undo`)).toHaveLength(0)
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText(/Lo que subió al remoto no se toca/)).toBeVisible()
    await user.click(within(dialog).getByRole('button', { name: es.runs.git.undo }))

    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/runs/${run.id}/git/undo`)[0].body).toEqual({
        confirm: true,
      }),
    )
    expect(await git.findByText(es.runs.git.undoneBadge)).toBeVisible()
    expect(git.queryByRole('button', { name: es.runs.git.undo })).not.toBeInTheDocument()
  })

  it('reports the branches it could not put back', async () => {
    const { run } = setup([row({ pushed: false })], {
      undoReport: {
        repos: {
          r1: {
            operation_id: null,
            items: [{ branch: 'agentic/T-1', result: 'skipped', reason: 'moved_since' }],
          },
        },
      },
    })
    const user = userEvent.setup()
    const git = await section(run.id)
    await user.click(git.getByRole('button', { name: es.runs.git.undo }))
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).queryByText(/Lo que subió al remoto/)).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: es.runs.git.undo }))
    expect(
      await screen.findByText(/Deshecho, salvo: agentic\/T-1 \(se ha movido después\)/),
    ).toBeVisible()
  })

  it('is not shown when the run did nothing with git', async () => {
    const { run } = setup([
      row({
        activity: activity({ commits: [], branches: [], tags: [], pushes: [] }),
        can_undo: false,
      }),
    ])
    renderApp(`/ejecuciones/${run.id}`)
    await screen.findByRole('region', { name: es.runs.events.title })
    await waitFor(() => expect(screen.queryByText(es.runs.git.title)).not.toBeInTheDocument())
    expect(screen.queryByRole('region', { name: es.runs.git.title })).not.toBeInTheDocument()
  })
})
