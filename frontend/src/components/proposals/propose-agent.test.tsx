import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Proposal } from '@/api/architect'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const P = es.proposals

function byAgent(): Proposal {
  return {
    id: 'prop-7',
    kind: 'new_agent',
    origin: 'agent',
    status: 'pending',
    reason: 'Hay textos en inglés.',
    conversation_id: null,
    source_agent_id: 'dev',
    source_run_id: 'r1',
    source_task_id: 't1',
    target_agent_id: 'draft-7',
    target_team_id: null,
    target_project_id: null,
    sheet: null,
    changes: [],
    new_skills: [],
    applied_fields: [],
    created_at: new Date().toISOString(),
    decided_at: null,
  }
}

describe('Agents that propose agents (phase 19, block 9)', () => {
  it('the permission is a switch of the Execution tab', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ agents: [makeAgent({ id: 'a1', name: 'Dev' })] })
    const user = userEvent.setup()
    renderApp('/agentes/a1/execution')
    await user.click(await screen.findByRole('switch', { name: es.agents.fields.proposeAgents }))
    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/agents/a1')[0]?.body).toEqual({
        can_propose_agents: true,
      }),
    )
  })

  it('a draft proposed by an agent says who, and why, and can go to the Architect', async () => {
    installFakeWebSocket()
    const draft = makeAgent({
      id: 'draft-7',
      name: 'Traductor',
      status: 'draft',
      proposal_id: 'prop-7',
      proposed_by: 'Dev',
    })
    const backend = createFakeBackend({ agents: [draft], architect: { proposals: [byAgent()] } })
    const user = userEvent.setup()
    const { router } = renderApp('/agentes')
    expect(await screen.findByText(P.chipAgent.replace('{{name}}', 'Dev'))).toBeVisible()
    await router.navigate('/agentes/draft-7/resumen')
    const banner = await screen.findByRole('region', { name: P.draftTitle })
    expect(within(banner).getByText(P.draftByAgent)).toBeVisible()
    expect(within(banner).getByText(/Hay textos en inglés\./)).toBeVisible()
    await user.click(within(banner).getByRole('button', { name: P.refine }))
    await waitFor(() =>
      expect(router.state.location.pathname).toMatch(/^\/agentes\/arquitecto\/conv-new-/),
    )
    expect(backend.callsTo('POST', '/api/architect/conversations')[0]?.body).toEqual({
      mode: 'agent',
      proposal_id: 'prop-7',
    })
  })
})
