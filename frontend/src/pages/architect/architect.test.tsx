import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makeInboxItem } from '@/test/fake-backend'
import { makeConversation, sheetState } from '@/test/fake-architect'
import { FakeWebSocket, installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const A = es.architect
const P = es.proposals

/** The socket of a conversation, opened, to push the events the backend would send. */
async function events(conversationId: string) {
  let socket: FakeWebSocket | undefined
  await waitFor(() => {
    socket = FakeWebSocket.instances.find((s) =>
      s.url.includes(`/conversations/${conversationId}/events`),
    )
    expect(socket).toBeDefined()
  })
  act(() => socket!.open())
  return (event: Record<string, unknown>) =>
    act(() => socket!.push({ conversation_id: conversationId, ...event } as never))
}

describe('Creating an agent with the Architect (phase 19, design §11)', () => {
  it('starts from Agentes and greets with an empty sheet, a composer with dictation', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ dictation: {} })
    const user = userEvent.setup()
    const { router } = renderApp('/agentes')
    await user.click(await screen.findByRole('link', { name: es.agents.architect }))
    await waitFor(() =>
      expect(router.state.location.pathname).toMatch(/^\/agentes\/arquitecto\/conv-new-/),
    )
    expect(backend.callsTo('POST', '/api/architect/conversations')).toHaveLength(1)
    expect(await screen.findByText(A.hello)).toBeVisible()
    const composer = screen.getByRole('textbox', { name: A.messageLabel })
    expect(
      within(composer.parentElement!).getByRole('button', { name: es.dictation.start }),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: A.draft })).toBeDisabled()
  })

  it('sends with Enter and shows the reply and the sheet live (CA2)', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ architect: { conversations: [makeConversation()] } })
    const user = userEvent.setup()
    renderApp('/agentes/arquitecto/conv-1')
    const composer = await screen.findByRole('textbox', { name: A.messageLabel })
    await user.type(composer, 'Quiero un redactor{Shift>}{Enter}{/Shift}para el blog{Enter}')
    await waitFor(() =>
      expect(
        backend.callsTo('POST', '/api/architect/conversations/conv-1/messages')[0]?.body,
      ).toEqual({
        text: 'Quiero un redactor\npara el blog',
      }),
    )
    expect(composer).toHaveValue('')
    const push = await events('conv-1')
    push({ type: 'state', state: 'thinking' })
    expect(await screen.findByText(A.thinking)).toBeVisible()
    push({ type: 'block', text: 'Le pongo **Redactor** de nombre.' })
    expect(await screen.findByText('Redactor', { selector: 'strong' })).toBeVisible()
    push({ type: 'sheet', ...sheetState({ name: 'Redactor', role: 'Redactor del blog' }) })
    const sheet = screen.getByRole('complementary', { name: A.sheet })
    expect(await within(sheet).findByText('Redactor del blog')).toBeVisible()
    push({
      type: 'message',
      message: {
        id: 'm9',
        role: 'architect',
        text: '¿Para qué público escribe?',
        tool_events: [{ fields: ['main.name', 'main.role'] }],
        created_at: new Date().toISOString(),
      },
    })
    push({ type: 'state', state: 'idle' })
    expect(await screen.findByText('¿Para qué público escribe?')).toBeVisible()
    expect(screen.getByText(A.changed.replace('{{fields}}', 'nombre, rol'))).toBeVisible()
    expect(screen.queryByText(A.thinking)).not.toBeInTheDocument()
  })

  it('an edit by hand locks the field, and the lock releases it', async () => {
    installFakeWebSocket()
    const conversation = makeConversation({
      sheet: sheetState({ name: 'Redactor', role: 'Redactor', description: 'Escribe posts' }),
    })
    const backend = createFakeBackend({ architect: { conversations: [conversation] } })
    const user = userEvent.setup()
    renderApp('/agentes/arquitecto/conv-1')
    const label = A.fields.description
    await user.click(
      await screen.findByRole('button', { name: A.edit.replace('{{field}}', label) }),
    )
    const field = screen.getByRole('textbox', { name: label })
    await user.clear(field)
    await user.type(field, 'Escribe posts cercanos')
    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(
        backend.callsTo('PATCH', '/api/architect/conversations/conv-1/sheet')[0]?.body,
      ).toEqual({
        patch: { description: 'Escribe posts cercanos' },
      }),
    )
    await user.click(
      await screen.findByRole('button', { name: A.unlock.replace('{{field}}', label) }),
    )
    await waitFor(() =>
      expect(
        backend.callsTo('POST', '/api/architect/conversations/conv-1/unlock')[0]?.body,
      ).toEqual({
        fields: ['main.description'],
      }),
    )
  })

  it('a ready sheet becomes a draft that is approved from its banner (CA5)', async () => {
    installFakeWebSocket()
    const conversation = makeConversation({
      sheet: sheetState({
        name: 'Redactor',
        role: 'Redactor',
        cli: 'claude',
        instructions: 'Escribe.',
      }),
    })
    const draft = makeAgent({
      id: 'draft-1',
      name: 'Redactor',
      status: 'draft',
      proposal_id: 'prop-1',
    })
    const backend = createFakeBackend({
      agents: [draft],
      architect: { conversations: [conversation], draftAgentId: 'draft-1' },
    })
    const user = userEvent.setup()
    const { router } = renderApp('/agentes/arquitecto/conv-1')
    await user.click(await screen.findByRole('button', { name: A.draft }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/agentes/draft-1/resumen'))
    const banner = await screen.findByRole('region', { name: P.draftTitle })
    expect(within(banner).getByRole('link', { name: P.openConversation })).toHaveAttribute(
      'href',
      '/agentes/arquitecto/conv-1',
    )
    await user.click(within(banner).getByRole('button', { name: P.approveAgent }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/proposals/prop-1/approve')).toHaveLength(1),
    )
  })

  it('the Inbox item of a proposal leads to the agent to review', async () => {
    installFakeWebSocket()
    createFakeBackend({
      agents: [
        makeAgent({ id: 'draft-1', name: 'Redactor', status: 'draft', proposal_id: 'prop-1' }),
      ],
      inbox: [
        makeInboxItem({
          id: 'i1',
          kind: 'proposal',
          title: 'Agente propuesto: Redactor',
          proposal_id: 'prop-1',
        }),
      ],
      architect: {
        conversations: [makeConversation()],
        proposals: [
          {
            id: 'prop-1',
            kind: 'new_agent',
            origin: 'architect',
            status: 'pending',
            reason: '',
            conversation_id: 'conv-1',
            source_agent_id: null,
            source_run_id: null,
            source_task_id: null,
            target_agent_id: 'draft-1',
            target_team_id: null,
            target_project_id: null,
            sheet: null,
            changes: [],
            new_skills: [],
            applied_fields: [],
            created_at: new Date().toISOString(),
            decided_at: null,
          },
        ],
      },
    })
    renderApp('/inbox')
    expect(await screen.findByRole('link', { name: es.inbox.reviewAgentProposal })).toHaveAttribute(
      'href',
      '/agentes/draft-1/resumen',
    )
  })

  it('Ajustes › Arquitecto saves the CLI and restores the default instructions', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({})
    const user = userEvent.setup()
    renderApp('/ajustes#architect')
    const section = await screen.findByRole('region', { name: A.settings.title })
    const idle = await within(section).findByRole('spinbutton', { name: A.settings.idle })
    await user.clear(idle)
    await user.type(idle, '30')
    await user.click(within(section).getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/architect')[0]?.body).toMatchObject({
        idle_minutes: 30,
      }),
    )
  })
})
