import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makeNote, makeProject } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

describe('Projects list', () => {
  it('lists projects with folder, branch and activity', async () => {
    createFakeBackend({
      projects: [
        makeProject({ name: 'Tienda online', git: { is_repo: true, branch: 'main', dirty: true } }),
        makeProject({
          name: 'Blog',
          path: 'D:\\blog',
          git: { is_repo: false, branch: null, dirty: false },
        }),
        makeProject({ name: 'Viejo', path: 'D:\\viejo', folder_exists: false, git: null }),
      ],
    })
    renderApp('/proyectos')
    const shop = await screen.findByRole('row', { name: 'Abrir Tienda online' })
    expect(within(shop).getByText('D:\\proyectos\\tienda')).toBeVisible()
    expect(within(shop).getByText('main')).toBeVisible()
    expect(within(shop).getByLabelText(es.projects.dirty)).toBeInTheDocument()
    expect(within(shop).getByText(es.time.justNow)).toBeVisible()
    const old = screen.getByRole('row', { name: 'Abrir Viejo' })
    expect(within(old).getByText(es.projects.folderMissing)).toBeVisible()
  })
})

describe('Project detail', () => {
  it('summary shows folder and git state, and opens the folder', async () => {
    const project = makeProject({ git: { is_repo: true, branch: 'develop', dirty: true } })
    const backend = createFakeBackend({ projects: [project] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/summary`)
    expect(await screen.findByRole('heading', { name: 'Tienda online' })).toBeVisible()
    expect(screen.getAllByText('develop').length).toBeGreaterThan(0)
    expect(screen.getByText(es.projects.summary.dirty)).toBeVisible()
    await user.click(screen.getByRole('button', { name: es.projects.openFolder }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/projects/${project.id}/open`)).toHaveLength(1),
    )
  })

  it('memory: lists the notes newest first, adds, edits and deletes them', async () => {
    const project = makeProject()
    const agent = makeAgent({ name: 'Dev', color: '#4FD1C5' })
    const older = makeNote({ text: 'Usa pnpm.', created_at: '2026-10-01T10:00:00Z' })
    const newer = makeNote({
      author_kind: 'agent',
      author_name: 'Dev',
      agent_id: agent.id,
      text: 'El login usa PKCE.',
      created_at: '2026-10-10T10:00:00Z',
    })
    const backend = createFakeBackend({
      projects: [project],
      agents: [agent],
      notes: { [project.id]: [older, newer] },
    })
    const base = `/api/projects/${project.id}/memory`
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/memory`)

    const cards = await screen.findAllByRole('article')
    expect(cards.map((c) => c.getAttribute('aria-label'))).toEqual(['Dev', es.projects.memory.you])

    await user.click(screen.getByRole('button', { name: es.projects.memory.add }))
    await user.type(screen.getByLabelText(es.projects.memory.noteLabel), 'Usar Stripe')
    await user.click(screen.getByRole('button', { name: es.projects.memory.save }))
    await waitFor(() => expect(backend.callsTo('POST', base)).toHaveLength(1))
    expect(backend.callsTo('POST', base)[0].body).toEqual({ text: 'Usar Stripe' })
    expect(await screen.findByText('Usar Stripe')).toBeVisible()

    const pnpm = screen.getByText('Usa pnpm.').closest('article')!
    await user.click(within(pnpm).getByRole('button', { name: es.projects.memory.edit }))
    const editor = within(pnpm).getByLabelText(es.projects.memory.noteLabel)
    await user.clear(editor)
    await user.type(editor, 'Usa pnpm 9.')
    await user.click(within(pnpm).getByRole('button', { name: es.projects.memory.save }))
    await waitFor(() => expect(backend.callsTo('PATCH', `${base}/${older.id}`)).toHaveLength(1))

    const login = screen.getByText('El login usa PKCE.').closest('article')!
    await user.click(within(login).getByRole('button', { name: es.projects.memory.delete }))
    await user.click(await screen.findByRole('button', { name: es.common.delete }))
    await waitFor(() => expect(backend.callsTo('DELETE', `${base}/${newer.id}`)).toHaveLength(1))
    await waitFor(() => expect(screen.queryByText('El login usa PKCE.')).toBeNull())
  })

  it('memory: warns when the agents cannot see every note', async () => {
    const project = makeProject()
    createFakeBackend({
      projects: [project],
      notes: { [project.id]: [makeNote({ text: 'x'.repeat(13000) })] },
    })
    renderApp(`/proyectos/${project.id}/memory`)
    expect(await screen.findByText(/solo ven las notas más recientes/)).toBeVisible()
  })

  it('settings: saves changes and removes the project after confirmation', async () => {
    const project = makeProject({ name: 'Blog' })
    const backend = createFakeBackend({ projects: [project] })
    const user = userEvent.setup()
    const { router } = renderApp(`/proyectos/${project.id}/settings`)

    await user.click(
      await screen.findByRole('radio', { name: new RegExp(es.projects.mode.worktree) }),
    )
    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', `/api/projects/${project.id}`)[0]?.body).toEqual({
        workspace_mode: 'worktree',
      }),
    )

    await user.click(screen.getByRole('button', { name: es.projects.delete.confirm }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: es.projects.delete.confirm }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/proyectos'))
    expect(backend.callsTo('DELETE', `/api/projects/${project.id}`)).toHaveLength(1)
  })

  it('breadcrumb shows the project name and links back to the list', async () => {
    const project = makeProject({ name: 'App reservas' })
    createFakeBackend({ projects: [project] })
    const user = userEvent.setup()
    const { router } = renderApp(`/proyectos/${project.id}/summary`)
    const crumbs = await screen.findByRole('navigation', { name: 'breadcrumb' })
    expect(await within(crumbs).findByText('App reservas')).toBeVisible()
    await user.click(within(crumbs).getByRole('link', { name: es.nav.projects }))
    expect(router.state.location.pathname).toBe('/proyectos')
  })
})
