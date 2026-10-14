import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeProject } from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { folderName } from './NewProjectDialog'

async function openDialog() {
  const user = userEvent.setup()
  const view = renderApp('/proyectos/nuevo')
  const dialog = await screen.findByRole('dialog')
  return { user, dialog, ...view }
}

describe('folderName', () => {
  it('is the last folder of the path', () => {
    expect(folderName('D:\\proyectos\\mi-web')).toBe('mi-web')
    expect(folderName('/home/ana/blog/')).toBe('blog')
    expect(folderName('')).toBe('')
  })
})

describe('New project dialog', () => {
  it('the empty state leads to it', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    renderApp('/proyectos')
    expect(await screen.findByText(es.pages.projects.emptyTitle)).toBeVisible()
    await user.click(screen.getAllByRole('button', { name: es.header.primary.newProject })[0])
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: es.projects.new.title })).toBeVisible()
  })

  it('/proyectos/nuevo still works: the list with the dialog open', async () => {
    createFakeBackend()
    const { router } = renderApp('/proyectos/nuevo')
    expect(await screen.findByRole('dialog')).toBeVisible()
    expect(router.state.location.pathname).toBe('/proyectos')
  })

  it('proposes the name from the folder, with the web pipeline by default', async () => {
    const backend = createFakeBackend()
    const { user, dialog, router } = await openDialog()
    await user.type(within(dialog).getByLabelText(es.projects.fields.path), 'D:\\proyectos\\mi-web')
    expect(within(dialog).getByLabelText(es.projects.fields.name)).toHaveValue('mi-web')
    await user.click(within(dialog).getByRole('button', { name: es.projects.new.submit }))

    await waitFor(() =>
      expect(router.state.location.pathname).toMatch(/^\/proyectos\/project-\d+\/summary$/),
    )
    expect(backend.callsTo('POST', '/api/projects')[0].body).toMatchObject({
      name: 'mi-web',
      path: 'D:\\proyectos\\mi-web',
      create_folder: false,
    })
    expect(backend.calls.some((c) => c.path.endsWith('/pipeline/template'))).toBe(true)
  })

  it('without pipeline and with the chosen colour', async () => {
    const backend = createFakeBackend()
    const { user, dialog } = await openDialog()
    await user.type(within(dialog).getByLabelText(es.projects.fields.path), 'D:\\blog')
    const name = within(dialog).getByLabelText(es.projects.fields.name)
    await user.clear(name)
    await user.type(name, 'Blog personal')
    await user.click(within(dialog).getByRole('radio', { name: /^Sin pipeline/ }))
    await user.click(within(dialog).getByRole('radio', { name: 'Color #F27FB2' }))
    await user.click(within(dialog).getByRole('button', { name: es.projects.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/projects')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/projects')[0].body).toMatchObject({
      name: 'Blog personal',
      color: '#F27FB2',
    })
    expect(backend.calls.some((c) => c.path.endsWith('/pipeline/template'))).toBe(false)
  })

  it('offers to create a missing folder and then creates the project', async () => {
    const backend = createFakeBackend()
    const { user, dialog, router } = await openDialog()
    await user.type(within(dialog).getByLabelText(es.projects.fields.name), 'Web')
    await user.type(within(dialog).getByLabelText(es.projects.fields.path), 'D:\\missing\\web')
    await user.click(within(dialog).getByRole('button', { name: es.projects.new.submit }))

    expect(await within(dialog).findByText(es.errors.folder_not_found)).toBeVisible()
    await user.click(within(dialog).getByRole('button', { name: es.projects.new.createFolder }))
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
    const { user, dialog } = await openDialog()
    await user.type(within(dialog).getByLabelText(es.projects.fields.name), 'Otra')
    await user.type(within(dialog).getByLabelText(es.projects.fields.path), 'd:\\TIENDA')
    await user.click(within(dialog).getByRole('button', { name: es.projects.new.submit }))
    expect(await within(dialog).findByText(es.errors.project_exists)).toBeVisible()
    expect(
      within(dialog).queryByRole('button', { name: es.projects.new.createFolder }),
    ).not.toBeInTheDocument()
  })

  it('requires name and folder', async () => {
    const backend = createFakeBackend()
    const { user, dialog } = await openDialog()
    await user.click(within(dialog).getByRole('button', { name: es.projects.new.submit }))
    expect(await within(dialog).findByText(es.errors.name_required)).toBeVisible()
    expect(within(dialog).getByText(es.common.required)).toBeVisible()
    expect(backend.callsTo('POST', '/api/projects')).toHaveLength(0)
  })
})
