import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import {
  createFakeBackend,
  makeAccount,
  makeAgent,
  makeTeam,
  systemAccounts,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'

const personal = () =>
  makeAccount({
    id: 'account-personal',
    cli: 'claude',
    name: 'marta.personal@gmail.com',
    plan: 'pro',
  })

function world() {
  const [claude, agy] = systemAccounts()
  const second = personal()
  const product = makeTeam({ name: 'Producto' })
  const contents = makeTeam({ name: 'Contenidos' })
  return { claude, agy, second, product, contents }
}

async function choose(
  user: ReturnType<typeof userEvent.setup>,
  trigger: HTMLElement,
  name: string | RegExp,
) {
  await user.click(trigger)
  await user.click(await screen.findByRole('option', { name }))
}

describe('Nuevo agente · equipo y cuenta', () => {
  it('creates the agent in a team and with the account chosen', async () => {
    const { claude, agy, second, product, contents } = world()
    const backend = createFakeBackend({
      agents: [makeAgent()],
      accounts: [claude, second, agy],
      teams: [product, contents],
    })
    const user = userEvent.setup()
    renderApp('/agentes')
    await user.click(await screen.findByRole('button', { name: es.header.primary.newAgent }))
    const dialog = await screen.findByRole('dialog')

    await user.type(within(dialog).getByLabelText(es.agents.fields.name), 'Redactor')
    await choose(
      user,
      within(dialog).getByRole('combobox', { name: es.agents.fields.team }),
      'Contenidos',
    )
    const account = within(dialog).getByRole('combobox', { name: es.agents.fields.account })
    // Without choosing, it uses the default account of its CLI, and says which.
    expect(account).toHaveTextContent('Predeterminada · Cuenta del sistema')
    await choose(user, account, /marta\.personal@gmail\.com/)
    await user.click(within(dialog).getByRole('button', { name: es.agents.new.submit }))

    await waitFor(() => expect(backend.callsTo('POST', '/api/agents')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/agents')[0].body).toMatchObject({
      name: 'Redactor',
      team_id: contents.id,
      account_id: second.id,
    })
  })

  it('changing the CLI drops the account of the other one', async () => {
    const { claude, agy, second } = world()
    const backend = createFakeBackend({
      agents: [makeAgent()],
      accounts: [claude, second, agy],
    })
    const user = userEvent.setup()
    renderApp('/agentes')
    await user.click(await screen.findByRole('button', { name: es.header.primary.newAgent }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(es.agents.fields.name), 'Gema')
    await choose(
      user,
      within(dialog).getByRole('combobox', { name: es.agents.fields.account }),
      /marta\.personal@gmail\.com/,
    )
    await choose(
      user,
      within(dialog).getByRole('combobox', { name: es.agents.fields.cli }),
      'Antigravity',
    )
    // agy has a single login: nothing to choose, and the Claude account is gone.
    const account = within(dialog).getByRole('combobox', { name: es.agents.fields.account })
    expect(account).toBeDisabled()
    await user.click(within(dialog).getByRole('button', { name: es.agents.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/agents')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/agents')[0].body).toMatchObject({
      cli: 'agy',
      account_id: null,
    })
  })
})

describe('Ficha del agente · equipo y cuenta', () => {
  it('saves the team from «General» and only the team', async () => {
    const { claude, agy, product } = world()
    const agent = makeAgent({ name: 'Dev' })
    const backend = createFakeBackend({
      agents: [agent],
      accounts: [claude, agy],
      teams: [product],
    })
    const user = userEvent.setup()
    renderApp(`/agentes/${agent.id}/general`)
    const team = await screen.findByRole('combobox', { name: es.agents.fields.team })
    expect(team).toHaveTextContent(es.teams.none)
    await choose(user, team, 'Producto')
    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() => expect(backend.callsTo('PATCH', `/api/agents/${agent.id}`)).toHaveLength(1))
    expect(backend.callsTo('PATCH', `/api/agents/${agent.id}`)[0].body).toEqual({
      team_id: product.id,
    })
  })

  it('«Ejecución» picks the account, and a new CLI goes back to the default one', async () => {
    const { claude, agy, second } = world()
    const agent = makeAgent({ name: 'Dev', account_id: second.id })
    const backend = createFakeBackend({ agents: [agent], accounts: [claude, second, agy] })
    const user = userEvent.setup()
    renderApp(`/agentes/${agent.id}/execution`)
    const account = await screen.findByRole('combobox', { name: es.agents.fields.account })
    await waitFor(() => expect(account).toHaveTextContent('marta.personal@gmail.com'))

    await user.click(screen.getByRole('radio', { name: /Antigravity/ }))
    expect(screen.getByRole('combobox', { name: es.agents.fields.account })).toHaveTextContent(
      'Predeterminada',
    )
    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() => expect(backend.callsTo('PATCH', `/api/agents/${agent.id}`)).toHaveLength(1))
    expect(backend.callsTo('PATCH', `/api/agents/${agent.id}`)[0].body).toMatchObject({
      cli: 'agy',
      account_id: null,
    })
  })

  it('the summary lists the team and the account in «Configuración», and the breadcrumb the team', async () => {
    const { claude, agy, second, product } = world()
    const agent = makeAgent({ name: 'Dev', team_id: product.id, account_id: second.id })
    createFakeBackend({
      agents: [agent],
      accounts: [claude, second, agy],
      teams: [{ ...product, agent_ids: [agent.id] }],
    })
    renderApp(`/agentes/${agent.id}/resumen`)
    const config = await screen.findByText(es.agents.summary.config)
    const details = config.closest('details') as HTMLElement
    // The disclosure is folded: its content is in the page, not on screen.
    expect(within(details).getByText(es.agents.fields.team)).toBeInTheDocument()
    expect(await within(details).findByText('Producto')).toBeInTheDocument()
    expect(await within(details).findByText('marta.personal@gmail.com')).toBeInTheDocument()
    // Inicio › Producto / Dev
    const trail = await screen.findByRole('navigation', { name: /breadcrumb/i })
    await waitFor(() => expect(trail).toHaveTextContent('Producto / Dev'))
  })

  it('the account of an agent without one is the default one of its CLI', async () => {
    const { claude, agy, second } = world()
    const agent = makeAgent({ name: 'Dev', account_id: null })
    createFakeBackend({ agents: [agent], accounts: [{ ...claude, name: 'Trabajo' }, second, agy] })
    renderApp(`/agentes/${agent.id}/resumen`)
    const details = (await screen.findByText(es.agents.summary.config)).closest(
      'details',
    ) as HTMLElement
    expect(await within(details).findByText('Trabajo')).toBeInTheDocument()
  })
})

describe('Lista de agentes · equipo', () => {
  it('shows the team of each agent and filters by team once there are teams', async () => {
    const { claude, agy, product } = world()
    const ana = makeAgent({ name: 'Ana', team_id: product.id })
    const dev = makeAgent({ name: 'Dev' })
    createFakeBackend({
      agents: [ana, dev],
      accounts: [claude, agy],
      teams: [{ ...product, agent_ids: [ana.id] }],
    })
    const user = userEvent.setup()
    const { router } = renderApp('/agentes')

    expect(await screen.findByRole('columnheader', { name: es.agents.columns.team })).toBeVisible()
    const rows = () => screen.getAllByRole('row').slice(1)
    expect(rows()).toHaveLength(2)
    expect(within(rows()[0]).getByText('Producto')).toBeVisible()
    expect(within(rows()[1]).getByText(es.teams.none)).toBeVisible()

    await choose(user, screen.getByRole('combobox', { name: es.agents.fields.team }), 'Producto')
    expect(rows()).toHaveLength(1)
    expect(router.state.location.search).toBe(`?equipo=${product.id}`)

    await choose(user, screen.getByRole('combobox', { name: es.agents.fields.team }), es.teams.none)
    expect(rows()).toHaveLength(1)
    expect(within(rows()[0]).getByText('Dev')).toBeVisible()
    expect(router.state.location.search).toBe('?equipo=sin')

    await choose(
      user,
      screen.getByRole('combobox', { name: es.agents.fields.team }),
      es.agents.allTeams,
    )
    expect(rows()).toHaveLength(2)
    expect(router.state.location.search).toBe('')
  })

  it('without teams there is neither the column nor the filter', async () => {
    createFakeBackend({ agents: [makeAgent()] })
    renderApp('/agentes')
    await screen.findByRole('columnheader', { name: es.agents.columns.agent })
    expect(screen.queryByRole('columnheader', { name: es.agents.columns.team })).toBeNull()
    expect(screen.queryByRole('combobox', { name: es.agents.fields.team })).toBeNull()
  })
})
