import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, TEMPLATES } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const T = es.agentTemplates

describe('Templates and agents as files (phase 19, block 7)', () => {
  it('saves an agent as a template from its page (CA8)', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ agents: [makeAgent({ id: 'a1', name: 'Redactor' })] })
    const user = userEvent.setup()
    renderApp('/agentes/a1/resumen')
    await user.click(await screen.findByRole('button', { name: es.common.more }))
    await user.click(await screen.findByRole('menuitem', { name: T.save }))
    const dialog = await screen.findByRole('alertdialog')
    const name = within(dialog).getByRole('textbox', { name: T.name })
    await user.clear(name)
    await user.type(name, 'Redactor base')
    await user.click(within(dialog).getByRole('button', { name: T.save }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/agents/a1/save-as-template')[0]?.body).toEqual({
        name: 'Redactor base',
      }),
    )
  })

  it("offers the person's templates next to the fixed ones, marked as theirs", async () => {
    installFakeWebSocket()
    createFakeBackend({
      ownTemplates: [
        {
          ...TEMPLATES[0],
          id: 'tpl-1',
          name: 'Mi redactor',
          own: true,
          skills: 2,
          connections: 1,
          documents: 0,
        },
      ],
    })
    renderApp('/agentes')
    const card = (await screen.findByText('Mi redactor')).closest('button')!
    expect(within(card).getByText(T.own)).toBeVisible()
  })

  it('imports a file as a draft after showing what is left out (CA9)', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({})
    const user = userEvent.setup()
    const { router } = renderApp('/agentes')
    await user.click(await screen.findByRole('button', { name: T.import.button }))
    const dialog = await screen.findByRole('dialog')
    const file = new File(
      [
        JSON.stringify({
          format: 'agentic-os.agent',
          version: 1,
          agent: { name: 'Traductor', role: 'Traductor', cli: 'claude' },
        }),
      ],
      'traductor.agent.json',
      { type: 'application/json' },
    )
    await user.upload(dialog.querySelector('input[type="file"]')!, file)
    expect(
      await within(dialog).findByText(T.import.missingSkill.replace('{{name}}', 'seo-basico')),
    ).toBeVisible()
    expect(within(dialog).getByRole('textbox', { name: es.agents.fields.name })).toHaveValue(
      'Traductor',
    )
    await user.click(within(dialog).getByRole('button', { name: T.import.run }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/agentes/imported-1/resumen'))
    expect(backend.callsTo('POST', '/api/agents/import')[0]?.body).toMatchObject({
      name: 'Traductor',
    })
  })

  it('refuses a file that is not JSON', async () => {
    installFakeWebSocket()
    createFakeBackend({})
    const user = userEvent.setup()
    renderApp('/agentes')
    await user.click(await screen.findByRole('button', { name: T.import.button }))
    const dialog = await screen.findByRole('dialog')
    await user.upload(
      dialog.querySelector('input[type="file"]')!,
      new File(['no es json'], 'x.json'),
    )
    expect(await screen.findByText(T.import.notJson)).toBeVisible()
  })
})
