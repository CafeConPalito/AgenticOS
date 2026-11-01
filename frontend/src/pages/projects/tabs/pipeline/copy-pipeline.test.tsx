import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makePipeline, makeProject } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

const C = es.pipeline.copy

describe('Copying the pipeline of another project (phase 24, CA8)', () => {
  it('previews the stages of the chosen project and copies them', async () => {
    const dev = makeAgent({ name: 'Dev' })
    const tienda = makeProject({ name: 'Tienda online' })
    const blog = makeProject({ name: 'Blog', path: 'D:\\blog' })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda, blog],
      pipelines: {
        [tienda.id]: makePipeline(tienda.id, [
          { id: 's1', name: 'Diseño', agent_id: dev.id, agent_name: 'Dev', exit_condition: 'x' },
          { id: 's2', name: 'Código', agent_id: dev.id, agent_name: 'Dev' },
        ]),
      },
    })
    const user = userEvent.setup()
    renderApp(`/proyectos/${blog.id}/pipeline`)

    await user.click(await screen.findByRole('button', { name: C.button }))
    const dialog = await screen.findByRole('dialog', { name: C.title })
    const submit = within(dialog).getByRole('button', { name: C.submit })
    expect(submit).toBeDisabled()
    await user.click(within(dialog).getByRole('combobox', { name: C.from }))
    await user.click(await screen.findByRole('option', { name: /Tienda online/ }))
    const preview = await within(dialog).findByRole('list', { name: C.preview })
    expect(preview).toHaveTextContent('Diseño')
    expect(preview).toHaveTextContent(es.pipeline.exit.badge)
    await user.click(submit)
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/projects/${blog.id}/pipeline/copy`)[0]?.body).toEqual({
        from_project_id: tienda.id,
      }),
    )
    expect(await screen.findByText(C.done)).toBeVisible()
  })
})
