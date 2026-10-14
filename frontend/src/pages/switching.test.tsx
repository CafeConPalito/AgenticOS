import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import {
  createFakeBackend,
  makeAccount,
  makeAgent,
  makeInboxItem,
  systemAccounts,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'

function world() {
  const [claude, agy] = systemAccounts()
  const second = makeAccount({ id: 'account-second', cli: 'claude', name: 'marta@gmail.com' })
  return { claude, agy, second }
}

async function choose(
  user: ReturnType<typeof userEvent.setup>,
  trigger: HTMLElement,
  name: string | RegExp,
) {
  await user.click(trigger)
  await user.click(await screen.findByRole('option', { name }))
}

describe('CLI secundario · formulario', () => {
  it('offers every account but the main one, and sends the secondary with its model', async () => {
    const { claude, agy, second } = world()
    const backend = createFakeBackend({
      agents: [makeAgent({ id: 'dev' })],
      accounts: [claude, second, agy],
    })
    const user = userEvent.setup()
    renderApp('/agentes')
    await user.click(await screen.findByRole('button', { name: es.header.primary.newAgent }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(es.agents.fields.name), 'Redactor')

    const trigger = within(dialog).getByRole('combobox', { name: es.agents.fields.fallback })
    await user.click(trigger)
    // The main account (the default of Claude Code) is not on offer.
    expect(screen.queryByRole('option', { name: /Cuenta del sistema/, hidden: false })).toBeTruthy()
    expect(screen.getAllByRole('option').map((o) => o.textContent)).not.toContain(
      'Claude Code · Cuenta del sistema',
    )
    await user.click(screen.getByRole('option', { name: /marta@gmail\.com/ }))
    await user.click(within(dialog).getByRole('button', { name: es.agents.new.submit }))

    await waitFor(() => expect(backend.callsTo('POST', '/api/agents')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/agents')[0].body).toMatchObject({
      fallback_account_id: second.id,
      fallback_model: '',
    })
  })

  it('shows it in the agent page, where it can be removed', async () => {
    const { claude, agy, second } = world()
    createFakeBackend({
      agents: [makeAgent({ id: 'dev', fallback_account_id: second.id })],
      accounts: [claude, second, agy],
    })
    const user = userEvent.setup()
    renderApp('/agentes/dev/execution')
    const select = await screen.findByRole('combobox', { name: es.agents.fields.fallback })
    await waitFor(() => expect(select).toHaveTextContent('marta@gmail.com'))
    await choose(user, select, es.agents.fields.fallbackNone)
    expect(
      screen.queryByRole('combobox', { name: es.agents.fields.fallbackModel }),
    ).not.toBeInTheDocument()
  })
})

describe('CLI secundario · alerta de cambio', () => {
  function pendingSwitch(options: string[]) {
    return makeInboxItem({
      id: 'switch-1',
      kind: 'switch',
      agent_id: 'dev',
      agent_name: 'Dev',
      title: 'Dev está a punto de agotar la cuota de Claude Code',
      detail: 'Va por el 93 %.',
      options,
    })
  }

  it('switches or stays from the request, with the accounts named in the buttons', async () => {
    const { claude, agy } = world()
    const backend = createFakeBackend({
      agents: [makeAgent({ id: 'dev', name: 'Dev', fallback_account_id: agy.id })],
      accounts: [claude, agy],
      inbox: [pendingSwitch(['Cambiar a Antigravity', 'Seguir con Claude Code'])],
    })
    const user = userEvent.setup()
    renderApp('/peticiones')
    await user.click(await screen.findByRole('button', { name: /Cambiar a Antigravity/ }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/inbox/switch-1/switch')).toHaveLength(1),
    )
    expect(backend.callsTo('POST', '/api/inbox/switch-1/switch')[0].body).toEqual({
      choice: 'switch',
    })
  })

  it('explains an unusable secondary and only lets the person dismiss it', async () => {
    const { claude, agy } = world()
    const backend = createFakeBackend({
      agents: [makeAgent({ id: 'dev', name: 'Dev', fallback_account_id: agy.id })],
      accounts: [claude, agy],
      inbox: [pendingSwitch([])],
    })
    const user = userEvent.setup()
    renderApp('/peticiones')
    expect(await screen.findByText(/Dev está a punto de agotar/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Cambiar a/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: es.inbox.understood }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/inbox/switch-1/dismiss')).toHaveLength(1),
    )
  })

  it('marks the agent that runs with its secondary on its card and lets it go back', async () => {
    const { claude, agy } = world()
    const backend = createFakeBackend({
      agents: [
        makeAgent({ id: 'dev', name: 'Dev', fallback_account_id: agy.id, using_fallback: true }),
      ],
      accounts: [claude, agy],
    })
    const user = userEvent.setup()
    renderApp('/')
    expect(await screen.findByText(es.home.agents.usingFallback)).toBeInTheDocument()
    renderApp('/agentes/dev')
    await user.click(await screen.findByRole('button', { name: es.agents.backToMain }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/agents/dev/fallback/clear')).toHaveLength(1),
    )
  })
})

describe('Ajustes · umbral de cambio', () => {
  it('saves the threshold', async () => {
    const { claude, agy } = world()
    const backend = createFakeBackend({ accounts: [claude, agy] })
    const user = userEvent.setup()
    renderApp('/ajustes')
    const input = await screen.findByLabelText(es.settings.limits.threshold.label)
    await waitFor(() => expect(input).toHaveValue('90'))
    await user.clear(input)
    await user.type(input, '75')
    await user.click(screen.getByRole('button', { name: es.settings.limits.threshold.save }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/switch-threshold')).toHaveLength(1),
    )
    expect(backend.callsTo('PUT', '/api/settings/switch-threshold')[0].body).toEqual({
      threshold: 75,
    })
  })
})
