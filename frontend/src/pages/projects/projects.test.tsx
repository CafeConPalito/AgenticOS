import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeProject } from '@/test/fake-backend'
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

  it('empty state leads to the new project form', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    const { router } = renderApp('/proyectos')
    expect(await screen.findByText(es.pages.projects.emptyTitle)).toBeVisible()
    await user.click(screen.getAllByRole('button', { name: es.header.primary.newProject })[0])
    expect(router.state.location.pathname).toBe('/proyectos/nuevo')
  })
})

describe('New project', () => {
  it('offers to create a missing folder and then creates the project', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    const { router } = renderApp('/proyectos/nuevo')
    await user.type(await screen.findByLabelText(es.projects.fields.name), 'Web')
    await user.type(screen.getByLabelText(es.projects.fields.path), 'D:\\missing\\web')
    await user.click(screen.getByRole('button', { name: es.common.create }))

    expect(await screen.findByText(es.errors.folder_not_found)).toBeVisible()
    await user.click(screen.getByRole('button', { name: es.projects.new.createFolder }))
    await waitFor(() =>
      expect(router.state.location.pathname).toMatch(/^\/proyectos\/project-\d+\/summary$/),
    )
    const posts = backend.callsTo('POST', '/api/projects')
    expect(posts).toHaveLength(2)
    expect(posts[1].body).toMatchObject({
      name: 'Web',
      path: 'D:\\missing\\web',
      create_folder: true,
    })
  })

  it('shows the duplicate-folder error on the path field', async () => {
    createFakeBackend({ projects: [makeProject({ path: 'D:\\tienda' })] })
    const user = userEvent.setup()
    renderApp('/proyectos/nuevo')
    await user.type(await screen.findByLabelText(es.projects.fields.name), 'Otra')
    await user.type(screen.getByLabelText(es.projects.fields.path), 'd:\\TIENDA')
    await user.click(screen.getByRole('button', { name: es.common.create }))
    expect(await screen.findByText(es.errors.project_exists)).toBeVisible()
    expect(
      screen.queryByRole('button', { name: es.projects.new.createFolder }),
    ).not.toBeInTheDocument()
  })

  it('requires name and folder', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/proyectos/nuevo')
    await user.click(await screen.findByRole('button', { name: es.common.create }))
    expect(await screen.findByText(es.errors.name_required)).toBeVisible()
    expect(screen.getByText(es.common.required)).toBeVisible()
    expect(backend.callsTo('POST', '/api/projects')).toHaveLength(0)
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

  it('saves the project memory', async () => {
    const project = makeProject({ memory: '' })
    const backend = createFakeBackend({ projects: [project] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/memory`)
    await user.type(await screen.findByLabelText(es.projects.fields.memory), 'Usar Stripe')
    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', `/api/projects/${project.id}`)).toHaveLength(1),
    )
    expect(backend.callsTo('PATCH', `/api/projects/${project.id}`)[0].body).toEqual({
      memory: 'Usar Stripe',
    })
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
