import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ConflictFile, OperationRead } from '@/api/git-integration'
import es from '@/i18n/es.json'
import {
  type FakeRepoGit,
  createFakeBackend,
  makeBranch,
  makeCommit,
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

const MERGED = [
  'antes',
  '<<<<<<< main',
  'nuestra',
  '=======',
  'suya',
  '>>>>>>> clash',
  'después',
].join('\n')

const CONFLICT: ConflictFile = {
  path: 'a.txt',
  base: 'antes\norig\ndespués',
  ours: 'antes\nnuestra\ndespués',
  theirs: 'antes\nsuya\ndespués',
  merged: MERGED,
  binary: false,
  ours_label: 'main',
  theirs_label: 'clash',
}

function operation(overrides: Partial<OperationRead> = {}): OperationRead {
  return {
    id: 'op-1',
    kind: 'merge',
    label: 'Merge de feature',
    at: new Date().toISOString(),
    group_id: null,
    undone: false,
    in_progress: false,
    blocked_by: null,
    lost_files: false,
    ...overrides,
  }
}

function setup(git: Record<string, FakeRepoGit>) {
  const project = makeProject()
  const repo = makeRepo({ id: 'r1', project_id: project.id, name: 'web' })
  const backend = createFakeBackend({
    projects: [project],
    repos: { [project.id]: [repo] },
    git: { r1: { ...git.r1, status: { branch: 'main', ...git.r1.status } } },
  })
  installFakeWebSocket()
  return { project, backend }
}

function open(projectId: string, section = 'changes') {
  renderApp(`/proyectos/${projectId}/git?section=${section}`)
}

describe('A merge that stopped', () => {
  it('lists the conflicts, resolves one in the editor and lets the merge continue', async () => {
    const { project, backend } = setup({
      r1: { status: { operation: 'merge' }, conflicts: { 'a.txt': CONFLICT } },
    })
    const user = userEvent.setup()
    open(project.id)

    const bar = await screen.findByRole('status', { name: es.git.operation.merge })
    const next = within(bar).getByRole('button', { name: es.git.operations.continue })
    expect(next).toBeDisabled() // a conflict is still open
    expect(
      within(bar).queryByRole('button', { name: es.git.operations.skip }),
    ).not.toBeInTheDocument()

    await user.click(within(bar).getByRole('button', { name: es.git.conflicts.resolve }))
    const editor = await screen.findByRole('dialog')
    expect(await within(editor).findByText('nuestra')).toBeVisible()
    expect(within(editor).getByText('suya')).toBeVisible()
    const save = within(editor).getByRole('button', { name: es.git.conflicts.markResolved })
    expect(save).toBeDisabled() // the markers are still in the result

    await user.click(within(editor).getByRole('button', { name: es.git.conflicts.acceptBoth }))
    const result = within(editor).getByRole('textbox', { name: es.git.conflicts.result })
    expect(result).toHaveValue('antes\nnuestra\nsuya\ndespués')
    expect(save).toBeEnabled()
    await user.click(save)

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/conflicts/resolve')[0].body).toEqual({
        path: 'a.txt',
        content: 'antes\nnuestra\nsuya\ndespués',
      }),
    )
    await waitFor(() =>
      expect(
        within(screen.getByRole('status', { name: es.git.operation.merge })).getByRole('button', {
          name: es.git.operations.continue,
        }),
      ).toBeEnabled(),
    )
    await user.click(
      within(screen.getByRole('status', { name: es.git.operation.merge })).getByRole('button', {
        name: es.git.operations.continue,
      }),
    )
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/operation/continue')).toHaveLength(1),
    )
  })

  it('edits the result by hand and keeps it while another block is chosen', async () => {
    const { project } = setup({
      r1: { status: { operation: 'merge' }, conflicts: { 'a.txt': CONFLICT } },
    })
    const user = userEvent.setup()
    open(project.id)
    await user.click(await screen.findByRole('button', { name: es.git.conflicts.resolve }))
    const editor = await screen.findByRole('dialog')
    const result = await within(editor).findByRole('textbox', { name: es.git.conflicts.result })

    await user.clear(result)
    await user.type(result, 'escrito a mano')
    expect(result).toHaveValue('escrito a mano')
    expect(
      within(editor).getByRole('button', { name: es.git.conflicts.markResolved }),
    ).toBeEnabled()

    await user.click(within(editor).getByRole('button', { name: es.git.conflicts.backToChoices }))
    expect(result).toHaveValue(MERGED) // back to the markers: nothing chosen
    expect(within(editor).getByRole('note')).toHaveTextContent('marcas de conflicto')
  })

  it('takes a whole side of the file', async () => {
    const { project, backend } = setup({
      r1: { status: { operation: 'merge' }, conflicts: { 'a.txt': CONFLICT } },
    })
    const user = userEvent.setup()
    open(project.id)
    await user.click(await screen.findByRole('button', { name: es.git.conflicts.resolve }))
    const editor = await screen.findByRole('dialog')

    await user.click(
      await within(editor).findByRole('button', { name: /Quedarme con toda la de clash/ }),
    )

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/conflicts/take')[0].body).toEqual({
        path: 'a.txt',
        side: 'theirs',
      }),
    )
  })

  it('aborts after asking', async () => {
    const { project, backend } = setup({
      r1: { status: { operation: 'rebase' }, conflicts: { 'a.txt': CONFLICT } },
    })
    const user = userEvent.setup()
    open(project.id)

    const bar = await screen.findByRole('status', { name: es.git.operation.rebase })
    expect(within(bar).getByRole('button', { name: es.git.operations.skip })).toBeVisible()
    await user.click(within(bar).getByRole('button', { name: es.git.operations.abort }))
    const dialog = await screen.findByRole('alertdialog')
    expect(backend.callsTo('POST', '/api/repos/r1/operation/abort')).toHaveLength(0)
    await user.click(within(dialog).getByRole('button', { name: es.git.operations.abort }))

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/operation/abort')).toHaveLength(1),
    )
  })
})

describe('Undo', () => {
  it('offers to undo the last operation and says what comes back', async () => {
    const { project, backend } = setup({
      r1: { operations: [operation({ lost_files: true, label: 'Reset duro' })] },
    })
    const user = userEvent.setup()
    open(project.id)

    await user.click(await screen.findByRole('button', { name: /Deshacer: Reset duro/ }))
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText(es.git.undo.withFiles)).toBeVisible()
    await user.click(within(dialog).getByRole('button', { name: es.git.undo.confirm }))

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/operations/op-1/undo')).toHaveLength(1),
    )
  })

  it('disables it, with the reason, when something moved since', async () => {
    const { project } = setup({
      r1: { operations: [operation({ blocked_by: 'moved_since' })] },
    })
    open(project.id)

    const button = await screen.findByRole('button', { name: /Deshacer: Merge de feature/ })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', es.git.undo.blocked.moved_since)
  })

  it('shows nothing when there is nothing to undo, or only things already undone', async () => {
    const { project } = setup({ r1: { operations: [operation({ undone: true })] } })
    open(project.id)

    await screen.findByRole('combobox', { name: es.git.branch })
    expect(screen.queryByRole('button', { name: /Deshacer:/ })).not.toBeInTheDocument()
  })
})

describe('Merge and rebase from the branches', () => {
  const branches = [makeBranch({ name: 'main', current: true }), makeBranch({ name: 'feature' })]

  it('merges another branch with the way the person chose', async () => {
    const { project, backend } = setup({ r1: { branches } })
    const user = userEvent.setup()
    open(project.id, 'branches')

    await user.click(await screen.findByRole('button', { name: `${es.git.merge.merge} feature` }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('textbox', { name: es.git.merge.message })).toHaveValue(
      'Merge de feature en main',
    )
    await user.click(within(dialog).getByRole('radio', { name: /Juntar en un solo commit/ }))
    expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: es.git.merge.merge }))

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/merge')[0].body).toEqual({
        ref: 'feature',
        mode: 'squash',
      }),
    )
  })

  it('says when a merge stopped on conflicts', async () => {
    const { project } = setup({
      r1: { branches, opResult: { status: 'conflicts', conflicts: ['a.txt'], message: '' } },
    })
    const user = userEvent.setup()
    open(project.id, 'branches')

    await user.click(await screen.findByRole('button', { name: `${es.git.merge.merge} feature` }))
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: es.git.merge.merge }),
    )

    expect(await screen.findByText(es.git.conflicts.more)).toBeVisible()
  })

  it('rebases the current branch onto another after asking', async () => {
    const { project, backend } = setup({ r1: { branches } })
    const user = userEvent.setup()
    open(project.id, 'branches')

    await user.click(await screen.findByRole('button', { name: `${es.git.merge.rebase} feature` }))
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText(/Rebase de main sobre feature/)).toBeVisible()
    await user.click(within(dialog).getByRole('button', { name: es.git.merge.rebase }))

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/rebase')[0].body).toEqual({ onto: 'feature' }),
    )
  })
})

describe('Actions on a commit', () => {
  const commits = [
    makeCommit({ sha: 'c'.repeat(40), subject: 'feat: login', parents: ['d'.repeat(40)] }),
    makeCommit({ sha: 'd'.repeat(40), subject: 'init' }),
  ]

  async function pickFirst(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByText('feat: login'))
    return screen.findByRole('group', { name: es.git.commitActions.title })
  }

  it('cherry-picks, reverts and branches from the commit', async () => {
    const { project, backend } = setup({ r1: { commits } })
    const user = userEvent.setup()
    open(project.id, 'history')
    const actions = await pickFirst(user)

    await user.click(within(actions).getByRole('button', { name: es.git.commitActions.cherryPick }))
    await user.click(within(actions).getByRole('button', { name: es.git.commitActions.revert }))
    await user.type(within(actions).getByLabelText(es.git.commitActions.branchHere), 'desde-aqui')
    await user.click(within(actions).getByRole('button', { name: es.git.branches.create }))

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/cherry-pick')).toHaveLength(1),
    )
    expect(backend.callsTo('POST', '/api/repos/r1/cherry-pick')[0].body).toEqual({
      shas: ['c'.repeat(40)],
    })
    expect(backend.callsTo('POST', '/api/repos/r1/revert')[0].body).toEqual({
      shas: ['c'.repeat(40)],
    })
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/branches')[0].body).toEqual({
        name: 'desde-aqui',
        start: 'c'.repeat(40),
      }),
    )
  })

  it('moves the branch softly at once, but asks before a hard reset', async () => {
    const { project, backend } = setup({ r1: { commits } })
    const user = userEvent.setup()
    open(project.id, 'history')
    const actions = await pickFirst(user)

    await user.click(within(actions).getByRole('button', { name: es.git.commitActions.reset }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/reset')[0].body).toMatchObject({
        mode: 'mixed',
        confirm: false,
      }),
    )

    await user.selectOptions(
      within(actions).getByLabelText(es.git.commitActions.resetMode),
      es.git.commitActions.modes.hard,
    )
    await user.click(within(actions).getByRole('button', { name: es.git.commitActions.reset }))
    const dialog = await screen.findByRole('alertdialog')
    expect(backend.callsTo('POST', '/api/repos/r1/reset')).toHaveLength(1)
    await user.click(within(dialog).getByRole('button', { name: es.git.commitActions.reset }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/repos/r1/reset')).toHaveLength(2))
    expect(backend.callsTo('POST', '/api/repos/r1/reset')[1].body).toMatchObject({
      mode: 'hard',
      confirm: true,
    })
  })

  it('rewrites the commits after it: reorder, reword and drop', async () => {
    const plan = [
      makeCommit({ sha: '1'.repeat(40), subject: 'primero' }),
      makeCommit({ sha: '2'.repeat(40), subject: 'segundo' }),
      makeCommit({ sha: '3'.repeat(40), subject: 'tercero' }),
    ]
    const { project, backend } = setup({ r1: { commits, plan } })
    const user = userEvent.setup()
    open(project.id, 'history')
    const actions = await pickFirst(user)

    await user.click(within(actions).getByRole('button', { name: es.git.commitActions.rewrite }))
    const sheet = await screen.findByRole('dialog')
    const list = await within(sheet).findByRole('list', { name: es.git.rebase.list })
    expect(within(list).getAllByRole('listitem')).toHaveLength(3)

    await user.click(within(sheet).getByRole('button', { name: `${es.git.rebase.down} 1111111` }))
    await user.selectOptions(
      within(sheet).getByLabelText(`${es.git.rebase.action} 3333333`),
      es.git.rebase.actions.drop,
    )
    await user.selectOptions(
      within(sheet).getByLabelText(`${es.git.rebase.action} 2222222`),
      es.git.rebase.actions.reword,
    )
    const message = within(sheet).getByLabelText(`${es.git.rebase.message} 2222222`)
    await user.clear(message)
    await user.type(message, 'segundo, mejor')
    expect(within(sheet).getByText('Se descartará 1 commit.')).toBeVisible()
    await user.click(within(sheet).getByRole('button', { name: es.git.rebase.start }))

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/rebase/interactive')[0].body).toEqual({
        base: 'd'.repeat(40),
        items: [
          { action: 'reword', sha: '2'.repeat(40), message: 'segundo, mejor' },
          { action: 'pick', sha: '1'.repeat(40) },
          { action: 'drop', sha: '3'.repeat(40) },
        ],
      }),
    )
  })

  it('does not let the first commit be folded into nothing', async () => {
    const plan = [
      makeCommit({ sha: '1'.repeat(40), subject: 'primero' }),
      makeCommit({ sha: '2'.repeat(40), subject: 'segundo' }),
    ]
    const { project } = setup({ r1: { commits, plan } })
    const user = userEvent.setup()
    open(project.id, 'history')
    const actions = await pickFirst(user)
    await user.click(within(actions).getByRole('button', { name: es.git.commitActions.rewrite }))
    const sheet = await screen.findByRole('dialog')

    await user.selectOptions(
      await within(sheet).findByLabelText(`${es.git.rebase.action} 1111111`),
      es.git.rebase.actions.squash,
    )

    expect(within(sheet).getByRole('note')).toHaveTextContent(es.git.rebase.firstFold)
    expect(within(sheet).getByRole('button', { name: es.git.rebase.start })).toBeDisabled()
  })
})
