import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Proposal } from '@/api/architect'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const P = es.proposals

function changes(): Proposal {
  return {
    id: 'prop-9',
    kind: 'agent_changes',
    origin: 'architect',
    status: 'pending',
    reason: '',
    conversation_id: 'conv-9',
    source_agent_id: null,
    source_run_id: null,
    source_task_id: null,
    target_agent_id: 'a1',
    target_team_id: null,
    target_project_id: null,
    sheet: null,
    changes: [
      {
        field: 'role',
        before: 'QA',
        after: 'QA estricto',
        current: 'QA manual',
        conflict: true,
        diff: '',
      },
      {
        field: 'instructions',
        before: 'Prueba.',
        after: 'Prueba.\nRechaza sin tests.',
        current: 'Prueba.',
        conflict: false,
        diff: '--- antes\n+++ después\n Prueba.\n+Rechaza sin tests.',
      },
    ],
    new_skills: [],
    applied_fields: [],
    created_at: new Date().toISOString(),
    decided_at: null,
  }
}

describe('Improving an active agent with the Architect (phase 19, block 8)', () => {
  it('starts an improvement conversation from the agent', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      agents: [makeAgent({ id: 'a1', name: 'QA', status: 'active' })],
    })
    const user = userEvent.setup()
    const { router } = renderApp('/agentes/a1/resumen')
    await user.click(await screen.findByRole('link', { name: es.architect.improve }))
    await waitFor(() =>
      expect(router.state.location.pathname).toMatch(/^\/agentes\/arquitecto\/conv-new-/),
    )
    expect(backend.callsTo('POST', '/api/architect/conversations')[0]?.body).toEqual({
      mode: 'improve_agent',
      agent_id: 'a1',
    })
  })

  it('reviews the changes field by field and settles a conflict before applying (CA12)', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      agents: [makeAgent({ id: 'a1', name: 'QA', status: 'active' })],
      architect: { proposals: [changes()] },
    })
    const user = userEvent.setup()
    renderApp('/agentes/a1/resumen')
    const banner = await screen.findByRole('region', { name: P.changesTitle })
    await user.click(within(banner).getByRole('button', { name: P.review }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('+Rechaza sin tests.')).toBeVisible()
    expect(within(dialog).getByText(P.conflict)).toBeVisible()
    const apply = within(dialog).getByRole('button', {
      name: P.applySelected.replace('{{count}}', '2'),
    })
    expect(apply).toBeDisabled()
    await user.click(within(dialog).getByRole('radio', { name: P.keepProposed }))
    // The instructions stay as they are: only the role is applied.
    await user.click(within(dialog).getByRole('switch', { name: es.architect.fields.instructions }))
    await user.click(
      within(dialog).getByRole('button', { name: P.applySelected.replace('{{count}}', '1') }),
    )
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/proposals/prop-9/approve')[0]?.body).toEqual({
        fields: ['role'],
        choices: { role: 'proposed' },
        skip_skills: [],
      }),
    )
  })

  it('lists the configuration changes in the History tab', async () => {
    installFakeWebSocket()
    createFakeBackend({
      agents: [makeAgent({ id: 'a1', name: 'QA', status: 'active' })],
      architect: {
        history: {
          a1: [
            {
              id: 'c1',
              source: 'architect',
              proposal_id: 'prop-9',
              conversation_id: 'conv-9',
              fields: { role: { before: 'QA', after: 'QA estricto' } },
              created_at: new Date().toISOString(),
            },
            {
              id: 'c2',
              source: 'user',
              proposal_id: null,
              conversation_id: null,
              fields: { fields: ['description'] },
              created_at: new Date().toISOString(),
            },
          ],
        },
      },
    })
    renderApp('/agentes/a1/history')
    const section = await screen.findByRole('region', { name: es.agents.configHistory.title })
    expect(within(section).getByText(/El Arquitecto · rol/)).toBeVisible()
    expect(within(section).getByText(/Editado a mano · descripción/)).toBeVisible()
    expect(within(section).getByRole('link', { name: P.openConversation })).toHaveAttribute(
      'href',
      '/agentes/arquitecto/conv-9',
    )
  })
})
