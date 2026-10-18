import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { type FakeRepoGit, createFakeBackend, makeProject, makeRepo } from '@/test/fake-backend'
import { FakeWebSocket, installFakeWebSocket } from '@/test/fake-socket'
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

const NOW = new Date().toISOString()

function setup(git: FakeRepoGit = {}, seed: { cloneError?: string } = {}) {
  const project = makeProject()
  const repo = makeRepo({ id: 'r1', project_id: project.id, name: 'web' })
  const backend = createFakeBackend({
    projects: [project],
    repos: { [project.id]: [repo] },
    git: { r1: { ...git, status: { branch: 'main', ...git.status } } },
    ...seed,
  })
  installFakeWebSocket()
  return { project, backend }
}

function open(projectId: string, section: string) {
  renderApp(`/proyectos/${projectId}/git?section=${section}`)
}

describe('Stash', () => {
  it('keeps the work aside, applies a stash and drops it after confirming', async () => {
    const { project, backend } = setup({
      stashes: [
        {
          index: 0,
          ref: 'stash@{0}',
          sha: 'a'.repeat(40),
          message: 'WIP: login',
          date: NOW,
          has_untracked: false,
        },
      ],
    })
    const user = userEvent.setup()
    open(project.id, 'stash')

    expect(await screen.findByText('WIP: login')).toBeVisible()
    await user.type(screen.getByLabelText(es.git.stash.message), 'a medias')
    await user.click(screen.getByRole('button', { name: es.git.stash.push }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/stashes')[0].body).toEqual({
        message: 'a medias',
        include_untracked: true,
      }),
    )

    await user.click(screen.getAllByRole('button', { name: es.git.stash.pop })[0])
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/stashes/apply')[0].body).toEqual({
        ref: 'stash@{0}',
        drop: true,
      }),
    )

    await user.click(screen.getByRole('button', { name: `${es.git.stash.drop} stash@{0}` }))
    expect(backend.callsTo('POST', '/api/repos/r1/stashes/drop')).toHaveLength(0)
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: es.git.stash.drop }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/stashes/drop')[0].body).toEqual({
        ref: 'stash@{0}',
        confirm: true,
      }),
    )
  })
})

describe('Tags', () => {
  it('creates an annotated tag, publishes it and deletes it after confirming', async () => {
    const { project, backend } = setup({
      tags: [{ name: 'v1.0', sha: 'b'.repeat(40), annotated: false, message: '', date: NOW }],
    })
    const user = userEvent.setup()
    open(project.id, 'tags')

    expect(await screen.findByText('v1.0')).toBeVisible()
    await user.type(screen.getByLabelText(es.git.tags.name), 'v1.1')
    await user.type(screen.getByLabelText(es.git.tags.message), 'segunda')
    await user.click(screen.getByRole('button', { name: es.git.tags.create }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/tags')[0].body).toEqual({
        name: 'v1.1',
        ref: undefined,
        message: 'segunda',
      }),
    )
    expect(await screen.findByText('v1.1')).toBeVisible()

    await user.click(screen.getByRole('button', { name: `${es.git.tags.publish} v1.0` }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/tags/remote')[0].body).toEqual({
        name: 'v1.0',
        delete: false,
      }),
    )

    await user.click(screen.getByRole('button', { name: `${es.git.tags.delete} v1.0` }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: es.git.tags.delete }))
    await waitFor(() =>
      expect(backend.callsTo('DELETE', '/api/repos/r1/tags/v1.0')).toHaveLength(1),
    )
  })
})

describe('Remotes and forced push', () => {
  const origin = { name: 'origin', fetch_url: 'git@host:a/b.git', push_url: 'git@host:a/b.git' }

  it('tests the connection of a remote', async () => {
    const { project, backend } = setup({ remotes: [origin] })
    const user = userEvent.setup()
    open(project.id, 'remotes')

    await user.click(await screen.findByRole('button', { name: `${es.git.remotes.test} origin` }))
    expect(await screen.findByText('Accesible (3 ramas)')).toBeVisible()
    expect(backend.callsTo('POST', '/api/repos/origin/test')).toHaveLength(0)
    expect(backend.callsTo('POST', '/api/repos/r1/remotes/origin/test')).toHaveLength(1)
  })

  it('shows what a forced push would destroy and only sends it once confirmed', async () => {
    const { project, backend } = setup({
      remotes: [origin],
      overwrites: ['abc1234', 'def5678'],
    })
    const user = userEvent.setup()
    open(project.id, 'remotes')

    await user.click(await screen.findByRole('button', { name: `Forzar el push de main` }))
    const dialog = await screen.findByRole('alertdialog')
    expect(
      await within(dialog).findByText(/Se perderían 2 commits.*abc1234, def5678/),
    ).toBeVisible()
    expect(backend.callsTo('POST', '/api/repos/r1/push/force')).toHaveLength(0)

    await user.click(within(dialog).getByRole('button', { name: es.git.remotes.forceConfirm }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/push/force')[0].body).toMatchObject({
        confirm: true,
      }),
    )
  })

  it('adds a remote', async () => {
    const { project, backend } = setup()
    const user = userEvent.setup()
    open(project.id, 'remotes')

    await user.type(await screen.findByLabelText(es.git.remotes.name), 'upstream')
    await user.type(screen.getByLabelText(es.git.remotes.url), 'https://host/x.git')
    await user.click(screen.getByRole('button', { name: es.git.remotes.add }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/remotes')[0].body).toEqual({
        name: 'upstream',
        url: 'https://host/x.git',
      }),
    )
  })
})

describe('Advanced', () => {
  it('lists submodules, LFS and worktrees; removing a submodule asks first', async () => {
    const { project, backend } = setup({
      submodules: [
        { path: 'libs/ui', sha: 'c'.repeat(40), describe: 'v2', state: 'modified', url: '' },
      ],
      lfs: { installed: true, used: true, patterns: ['*.psd'], files: 2 },
      worktrees: [
        {
          path: 'D:\\web',
          head: null,
          branch: 'main',
          main: true,
          locked: false,
          prunable: false,
          task: false,
        },
        {
          path: 'D:\\web.wt\\T-1',
          head: null,
          branch: 'agentic/T-1',
          main: false,
          locked: false,
          prunable: false,
          task: true,
        },
      ],
    })
    const user = userEvent.setup()
    open(project.id, 'advanced')

    expect(await screen.findByText('libs/ui')).toBeVisible()
    expect(screen.getByText(es.git.advanced.submoduleState.modified)).toBeVisible()
    expect(screen.getByText('*.psd')).toBeVisible()
    expect(screen.getByText(es.git.advanced.taskTree)).toBeVisible()
    // The main worktree cannot be removed.
    expect(
      screen.queryByRole('button', { name: `${es.git.advanced.removeTree} D:\\web` }),
    ).not.toBeInTheDocument()

    await user.click(
      screen.getByRole('button', { name: `${es.git.advanced.removeSubmodule} libs/ui` }),
    )
    expect(backend.callsTo('POST', '/api/repos/r1/submodules/remove')).toHaveLength(0)
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: es.git.advanced.removeSubmodule }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/submodules/remove')[0].body).toEqual({
        path: 'libs/ui',
        confirm: true,
      }),
    )
  })

  it('says so when Git LFS is not installed', async () => {
    const { project } = setup({ lfs: { installed: false, used: false, patterns: [], files: 0 } })
    open(project.id, 'advanced')
    expect(await screen.findByText(es.git.advanced.lfsMissing)).toBeVisible()
  })
})

describe('Maintenance', () => {
  it('previews what the cleaning deletes and sends exactly that after confirming', async () => {
    const { project, backend } = setup({
      clean: { files: ['notes.tmp'], folders: ['build/'] },
    })
    const user = userEvent.setup()
    open(project.id, 'maintenance')

    const list = await screen.findByRole('list', { name: es.git.maintenance.willDelete })
    expect(
      within(list)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['notes.tmp', 'build/'])
    await user.click(screen.getByRole('button', { name: 'Borrar 2 elementos' }))
    expect(backend.callsTo('POST', '/api/repos/r1/clean')).toHaveLength(0)
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: es.git.maintenance.cleanConfirm }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/repos/r1/clean')[0].body).toEqual({
        paths: ['notes.tmp', 'build/'],
        folders: true,
        ignored: false,
        confirm: true,
      }),
    )
  })

  it('checks the integrity of the repository', async () => {
    const { project } = setup()
    const user = userEvent.setup()
    open(project.id, 'maintenance')
    await user.click(await screen.findByRole('button', { name: es.git.maintenance.verify }))
    expect(await screen.findByText(es.git.maintenance.verifyOk)).toBeVisible()
  })
})

describe('Settings', () => {
  it('shows each scope and saves only what changed; empty removes the setting', async () => {
    const { project, backend } = setup({
      config: { 'user.name': { global: 'Ana', local: null } },
    })
    const user = userEvent.setup()
    open(project.id, 'settings')

    const local = await screen.findByRole('textbox', {
      name: `user.name (${es.git.settings.scope.local})`,
    })
    const global = screen.getByRole('textbox', {
      name: `user.name (${es.git.settings.scope.global})`,
    })
    expect(global).toHaveValue('Ana')
    expect(local).toHaveValue('')
    expect(screen.queryByRole('button', { name: es.common.save })).not.toBeInTheDocument()

    await user.type(local, 'Ana del repo')
    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/repos/r1/config')[0].body).toEqual({
        scope: 'local',
        key: 'user.name',
        value: 'Ana del repo',
      }),
    )

    await user.clear(global)
    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/repos/r1/config')[1].body).toEqual({
        scope: 'global',
        key: 'user.name',
        value: null,
      }),
    )
  })
})

describe('Git terminal', () => {
  it('opens a shell in the repository and closes it when asked', async () => {
    const { project, backend } = setup()
    const user = userEvent.setup()
    open(project.id, 'terminal')

    await user.click(await screen.findByRole('button', { name: es.git.terminal.open }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/repos/r1/shell')).toHaveLength(1))
    await waitFor(() =>
      expect(
        FakeWebSocket.instances.some((ws) => ws.url.includes('/api/git/shells/sh-1/terminal')),
      ).toBe(true),
    )
    expect(screen.getByRole('region', { name: es.git.terminal.label })).toBeVisible()

    await user.click(screen.getByRole('button', { name: es.git.terminal.close }))
    await waitFor(() => expect(backend.callsTo('DELETE', '/api/git/shells/sh-1')).toHaveLength(1))
    expect(await screen.findByRole('button', { name: es.git.terminal.open })).toBeVisible()
  })
})

describe('Clone from URL', () => {
  async function openClone() {
    const user = userEvent.setup()
    const view = renderApp('/proyectos/nuevo')
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('radio', { name: es.projects.new.sources.clone }))
    return { user, dialog, ...view }
  }

  it('clones, waits for it and creates the project in the new folder', async () => {
    const backend = createFakeBackend()
    installFakeWebSocket()
    const { user, dialog, router } = await openClone()

    await user.type(
      within(dialog).getByLabelText(es.projects.new.url),
      'https://github.com/ana/mi-web.git',
    )
    expect(within(dialog).getByLabelText(es.projects.fields.name)).toHaveValue('mi-web')
    await user.type(within(dialog).getByLabelText(es.projects.new.parent), 'D:\\proyectos')
    await user.click(within(dialog).getByRole('button', { name: es.projects.new.cloneSubmit }))

    await waitFor(
      () => expect(router.state.location.pathname).toMatch(/^\/proyectos\/project-\d+\/summary$/),
      { timeout: 5000 },
    )
    expect(backend.callsTo('POST', '/api/git/clone')[0].body).toEqual({
      url: 'https://github.com/ana/mi-web.git',
      parent_folder: 'D:\\proyectos',
      name: 'mi-web',
    })
    expect(backend.callsTo('POST', '/api/projects')[0].body).toMatchObject({
      name: 'mi-web',
      path: 'D:\\proyectos/mi-web',
    })
  })

  it('does not create the project when the clone fails, and says why', async () => {
    const backend = createFakeBackend({ cloneError: 'auth_failed' })
    installFakeWebSocket()
    const { user, dialog } = await openClone()

    await user.type(within(dialog).getByLabelText(es.projects.new.url), 'git@host:a/privado.git')
    await user.type(within(dialog).getByLabelText(es.projects.new.parent), 'D:\\proyectos')
    await user.click(within(dialog).getByRole('button', { name: es.projects.new.cloneSubmit }))

    expect(
      await within(dialog).findByRole('alert', undefined, { timeout: 5000 }),
    ).toHaveTextContent(es.git.errors.auth_failed)
    expect(backend.callsTo('POST', '/api/projects')).toHaveLength(0)
  })

  it('asks for the URL before cloning', async () => {
    const backend = createFakeBackend()
    const { user, dialog } = await openClone()
    await user.type(within(dialog).getByLabelText(es.projects.new.parent), 'D:\\proyectos')
    await user.click(within(dialog).getByRole('button', { name: es.projects.new.cloneSubmit }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(es.projects.new.urlRequired)
    expect(backend.callsTo('POST', '/api/git/clone')).toHaveLength(0)
  })
})
