import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeProject, makeRepo } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

describe('Repositories of a project', () => {
  it('lists them in the settings with their base branch and where they are', async () => {
    const project = makeProject()
    createFakeBackend({
      projects: [project],
      repos: {
        [project.id]: [
          makeRepo({ project_id: project.id, name: 'backend', rel_path: 'backend' }),
          makeRepo({
            project_id: project.id,
            name: 'Shared lib',
            rel_path: null,
            linked: true,
            path: 'D:\\libs\\shared',
            base_branch: 'develop',
          }),
          makeRepo({ project_id: project.id, name: 'old', rel_path: 'old', missing: true }),
        ],
      },
    })
    renderApp(`/proyectos/${project.id}/settings`)

    const section = await screen.findByRole('region', { name: es.projects.repos.title })
    expect(await within(section).findByText('Shared lib')).toBeVisible()
    expect(within(section).getAllByText('backend')).toHaveLength(2) // its name and its folder
    expect(within(section).getByText('D:\\libs\\shared')).toBeVisible()
    expect(within(section).getByText(es.projects.repos.badgeLinked)).toBeVisible()
    expect(within(section).getByText(es.projects.repos.badgeMissing)).toBeVisible()
    expect(within(section).getByLabelText(`${es.projects.repos.base} Shared lib`)).toHaveValue(
      'develop',
    )
  })

  it('edits the base branch, the pull mode and whether it takes part in tasks', async () => {
    const project = makeProject()
    const backend = createFakeBackend({
      projects: [project],
      repos: { [project.id]: [makeRepo({ id: 'r1', project_id: project.id, name: 'backend' })] },
    })
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/settings`)

    const base = await screen.findByLabelText(`${es.projects.repos.base} backend`)
    await user.clear(base)
    await user.type(base, 'develop')
    await user.tab() // leaving the field saves it
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/repos/r1').at(-1)?.body).toEqual({
        base_branch: 'develop',
      }),
    )

    await user.selectOptions(
      screen.getByLabelText(`${es.projects.repos.pull} backend`),
      es.projects.repos.pullMode.rebase,
    )
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/repos/r1').at(-1)?.body).toEqual({
        pull_mode: 'rebase',
      }),
    )

    await user.click(
      screen.getByRole('switch', { name: `${es.projects.repos.participates} backend` }),
    )
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/repos/r1').at(-1)?.body).toEqual({
        participates: false,
      }),
    )
  })

  it('links a repository from outside the folder and removes one after confirming', async () => {
    const project = makeProject()
    const backend = createFakeBackend({
      projects: [project],
      repos: { [project.id]: [makeRepo({ id: 'r1', project_id: project.id, name: 'backend' })] },
    })
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/settings`)
    await screen.findByText('backend')

    await user.click(screen.getByRole('button', { name: es.projects.repos.link }))
    await user.type(screen.getByLabelText(es.projects.repos.linkHelp), 'D:\\libs\\shared')
    await user.click(screen.getByRole('button', { name: es.projects.repos.linkConfirm }))
    expect(await screen.findByText('shared')).toBeVisible()
    expect(backend.callsTo('POST', `/api/projects/${project.id}/repos`)[0].body).toEqual({
      path: 'D:\\libs\\shared',
    })

    await user.click(screen.getByRole('button', { name: `${es.projects.repos.remove} backend` }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: es.projects.repos.remove }))
    await waitFor(() => expect(screen.queryByText('backend')).not.toBeInTheDocument())
    expect(backend.callsTo('DELETE', '/api/repos/r1')).toHaveLength(1)
  })

  it('looks for the repositories again', async () => {
    const project = makeProject()
    const backend = createFakeBackend({ projects: [project], repos: { [project.id]: [] } })
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/settings`)

    expect(await screen.findByText(es.projects.repos.none)).toBeVisible()
    await user.click(screen.getByRole('button', { name: es.projects.repos.scan }))

    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/projects/${project.id}/repos/scan`)).toHaveLength(1),
    )
  })

  it('the summary lists every repository with its branch when there are several', async () => {
    const project = makeProject()
    createFakeBackend({
      projects: [project],
      repos: {
        [project.id]: [
          makeRepo({
            project_id: project.id,
            name: 'backend',
            git: { is_repo: true, branch: 'feat/x', dirty: true },
          }),
          makeRepo({ project_id: project.id, name: 'frontend' }),
        ],
      },
    })
    renderApp(`/proyectos/${project.id}/summary`)

    expect(await screen.findByText(/feat\/x/)).toBeVisible()
    expect(screen.getByText('frontend')).toBeVisible()
    expect(screen.queryByText(es.projects.summary.repo)).not.toBeInTheDocument()
  })
})
