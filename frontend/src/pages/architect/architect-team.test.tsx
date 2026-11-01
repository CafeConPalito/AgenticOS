import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Proposal } from '@/api/architect'
import es from '@/i18n/es.json'
import { createFakeBackend } from '@/test/fake-backend'
import { emptySheet, makeConversation } from '@/test/fake-architect'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const A = es.architect
const P = es.proposals

function teamConversation() {
  const sheet = {
    ...emptySheet(),
    agents: {
      writer: { name: 'Redactor', role: 'Escribe posts', cli: 'claude' as const },
    },
    team: { name: 'Contenidos', description: 'Publica el blog' },
    pipeline: {
      project_id: 'p1',
      project_name: 'Blog',
      stages: [
        { name: 'Escribir', agent: 'ref:writer' },
        { name: 'Revisar', agent: 'ref:writer', requires_review: true },
      ],
      links: null,
    },
  }
  return makeConversation({
    id: 'conv-team',
    mode: 'team',
    sheet: {
      sheet,
      issues: [],
      progress: { writer: 80 },
      ready: true,
      locked: [],
      pipeline_layout: { '0': [0, 0], '1': [260, 0] },
    },
  })
}

function teamProposal(conflict: boolean): Proposal {
  return {
    id: 'prop-team',
    kind: 'team',
    origin: 'architect',
    status: 'pending',
    reason: '',
    conversation_id: 'conv-team',
    source_agent_id: null,
    source_run_id: null,
    source_task_id: null,
    target_agent_id: null,
    target_team_id: null,
    target_project_id: 'p1',
    sheet: null,
    changes: [],
    new_skills: [],
    applied_fields: [],
    created_at: new Date().toISOString(),
    decided_at: null,
    team: {
      team: { name: 'Contenidos', description: 'Publica el blog' },
      new_agents: [
        { ref: 'writer', id: 'a-w', name: 'Redactor', role: 'Escribe posts', model: '' },
        { ref: 'editor', id: 'a-e', name: 'Editor', role: 'Corrige', model: '' },
      ],
      existing_agents: [],
      pipeline: {
        project_id: 'p1',
        project_name: 'Blog',
        stages: [{ name: 'Escribir', agent: 'Redactor' }],
        added: ['Escribir'],
        removed: [],
        changed: [],
        links_changed: false,
        conflict,
      },
    },
  }
}

describe('Teams and pipelines with the Architect (phase 19, block 10)', () => {
  it('shows the team sheet in tabs with the pipeline preview', async () => {
    installFakeWebSocket()
    createFakeBackend({ architect: { conversations: [teamConversation()] } })
    const user = userEvent.setup()
    renderApp('/agentes/arquitecto/conv-team')
    const sheet = await screen.findByRole('complementary', { name: A.teamSheet })
    expect(within(sheet).getByText('Contenidos')).toBeVisible()
    await user.click(within(sheet).getByRole('tab', { name: A.tabs.agents }))
    expect(await within(sheet).findByText('Redactor')).toBeVisible()
    await user.click(within(sheet).getByRole('tab', { name: A.tabs.pipeline }))
    expect(await within(sheet).findByTestId('pipeline-preview')).toBeInTheDocument()
    expect(within(sheet).getByRole('button', { name: A.proposeTeam })).toBeEnabled()
  })

  it('the review leaves a new agent out and makes the person settle a conflict', async () => {
    installFakeWebSocket()
    const conversation = {
      ...teamConversation(),
      status: 'proposed' as const,
      proposal_id: 'prop-team',
    }
    const backend = createFakeBackend({
      architect: { conversations: [conversation], proposals: [teamProposal(true)] },
    })
    const user = userEvent.setup()
    renderApp('/agentes/arquitecto/conv-team')
    await user.click(await screen.findByRole('button', { name: P.reviewTeam }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('switch', { name: /Editor/ }))
    const approve = within(dialog).getByRole('button', { name: P.approveTeam })
    expect(approve).toBeDisabled()
    await user.click(within(dialog).getByRole('radio', { name: P.keepProposed }))
    await user.click(approve)
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/proposals/prop-team/approve')[0]?.body).toEqual({
        skip_agents: ['editor'],
        choices: { pipeline: 'proposed' },
      }),
    )
  })

  it('starts a team conversation from the list', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({})
    const user = userEvent.setup()
    renderApp('/agentes/arquitecto')
    await user.click(await screen.findByRole('button', { name: A.newTeam }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/architect/conversations')[0]?.body).toEqual({
        mode: 'team',
      }),
    )
  })

  it('designs the pipeline of a project from its tab (phase 24)', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({})
    renderApp('/agentes/arquitecto?disenar=p1')
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/architect/conversations')[0]?.body).toEqual({
        mode: 'team',
        project_id: 'p1',
      }),
    )
  })

  it('Agentes offers a new team with the Architect (phase 24)', async () => {
    createFakeBackend({})
    renderApp('/agentes')
    expect(await screen.findByRole('link', { name: es.teams.withArchitect })).toHaveAttribute(
      'href',
      '/agentes/arquitecto?equipo',
    )
  })

  it('improving a team or a pipeline starts the matching conversation', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({})
    renderApp('/agentes/arquitecto?equipo=t1')
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/architect/conversations')[0]?.body).toEqual({
        mode: 'improve_team',
        team_id: 't1',
      }),
    )
  })
})
