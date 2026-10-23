import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import docSheet from '@/components/knowledge/DocSheet.tsx?raw'
import proposalReview from '@/components/knowledge/ProposalReview.tsx?raw'
import newAgent from '@/pages/agents/NewAgentDialog.tsx?raw'
import generalTab from '@/pages/agents/tabs/GeneralTab.tsx?raw'
import memoryTab from '@/pages/projects/tabs/MemoryTab.tsx?raw'
import launchRun from '@/pages/runs/LaunchRunDialog.tsx?raw'
import newTask from '@/pages/tasks/NewTaskDialog.tsx?raw'
import taskPage from '@/pages/tasks/TaskPage.tsx?raw'
import { MarkdownEditor } from '@/components/MarkdownEditor'
import es from '@/i18n/es.json'
import { resetDictation, setRecorder } from '@/lib/dictation/controller'
import { Providers } from '@/providers'
import { createFakeBackend, makeInboxItem } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

const MIC = es.dictation

beforeEach(() => {
  resetDictation()
  setRecorder({
    start: vi.fn(async () => ({
      stop: async () => new Blob(['wav'], { type: 'audio/wav' }),
      cancel: vi.fn(),
    })),
  })
})

describe('the fields that can be dictated', () => {
  it('the Markdown editor (agent instructions, proposal text) has a microphone', async () => {
    createFakeBackend({ dictation: {} })
    render(
      <Providers>
        <MarkdownEditor value="" onChange={() => {}} />
      </Providers>,
    )
    expect(await screen.findByRole('button', { name: MIC.start })).toBeInTheDocument()
  })

  it('no field shows a microphone while dictation is off', async () => {
    createFakeBackend({})
    render(
      <Providers>
        <MarkdownEditor value="" onChange={() => {}} />
      </Providers>,
    )
    await waitFor(() => expect(screen.getByRole('textbox')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: MIC.start })).not.toBeInTheDocument()
  })

  it('the answer to an agent in the Inbox is dictated, grows, and Enter sends it', async () => {
    const question = makeInboxItem({ kind: 'question', title: '¿Postgres o SQLite?' })
    const backend = createFakeBackend({
      inbox: [question],
      dictation: { answers: ['SQLite, por simplicidad'] },
    })
    const user = userEvent.setup()
    renderApp('/inbox')
    const card = await screen.findByRole('article', {
      name: `${es.inbox.kinds.question}: ¿Postgres o SQLite?`,
    })
    const field = within(card).getByLabelText(es.inbox.answerPlaceholder)
    expect(field.tagName).toBe('TEXTAREA')
    await user.click(await within(card).findByRole('button', { name: MIC.start }))
    await user.click(await within(card).findByRole('button', { name: MIC.stop }))
    await waitFor(() => expect(field).toHaveValue('SQLite, por simplicidad'))
    // Shift+Enter is a new line; Enter sends.
    await user.type(field, '{Shift>}{Enter}{/Shift}y rápido')
    expect(field).toHaveValue('SQLite, por simplicidad\ny rápido')
    expect(backend.callsTo('POST', `/api/inbox/${question.id}/answer`)).toHaveLength(0)
    await user.type(field, '{Enter}')
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/inbox/${question.id}/answer`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/inbox/${question.id}/answer`)[0].body).toEqual({
      text: 'SQLite, por simplicidad\ny rápido',
    })
  })

  it('Enter does not send an empty answer', async () => {
    const question = makeInboxItem({ kind: 'question', title: '¿Postgres o SQLite?' })
    const backend = createFakeBackend({ inbox: [question], dictation: {} })
    const user = userEvent.setup()
    renderApp('/inbox')
    const card = await screen.findByRole('article', {
      name: `${es.inbox.kinds.question}: ¿Postgres o SQLite?`,
    })
    await user.type(within(card).getByLabelText(es.inbox.answerPlaceholder), '{Enter}')
    expect(backend.callsTo('POST', `/api/inbox/${question.id}/answer`)).toHaveLength(0)
  })

  it('Enter does not reject a review without a reason', async () => {
    const review = makeInboxItem({
      kind: 'review',
      title: 'Revisar',
      task_id: 't',
      task_code: 'T-1',
    })
    const backend = createFakeBackend({ inbox: [review], dictation: {} })
    const user = userEvent.setup()
    renderApp('/inbox')
    const card = await screen.findByRole('article', { name: `${es.inbox.kinds.review}: Revisar` })
    await user.click(await within(card).findByRole('button', { name: es.inbox.reviewReject }))
    await user.type(within(card).getByLabelText(es.inbox.reasonPlaceholder), '{Enter}')
    expect(backend.callsTo('POST', `/api/inbox/${review.id}/review`)).toHaveLength(0)
  })

  it('the reason for rejecting a review in the Inbox can be dictated', async () => {
    const review = makeInboxItem({
      kind: 'review',
      title: 'Revisar la etapa',
      task_id: 'task-1',
      task_code: 'T-1',
    })
    createFakeBackend({ inbox: [review], dictation: {} })
    const user = userEvent.setup()
    renderApp('/inbox')
    const card = await screen.findByRole('article', {
      name: `${es.inbox.kinds.review}: Revisar la etapa`,
    })
    await user.click(await within(card).findByRole('button', { name: es.inbox.reviewReject }))
    expect(within(card).getByLabelText(es.inbox.reasonPlaceholder).tagName).toBe('TEXTAREA')
    expect(await within(card).findByRole('button', { name: MIC.start })).toBeInTheDocument()
  })

  it('the description of a new task (opened with N) has a microphone', async () => {
    createFakeBackend({ dictation: {} })
    const user = userEvent.setup()
    renderApp('/')
    await screen.findAllByRole('main')
    await user.keyboard('n')
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.addDescription }))
    expect(await within(dialog).findByRole('button', { name: MIC.start })).toBeInTheDocument()
  })

  // The remaining fields are checked in the source: they are inside dialogs and tabs that need a
  // lot of data to open, and what matters is that none loses its microphone.
  it.each([
    ['NewTaskDialog', newTask, 'id="task-description"'],
    ['TaskPage', taskPage, 'id="complete-summary"'],
    ['TaskPage', taskPage, 'id="reject-reason"'],
    ['NewAgentDialog', newAgent, 'id="new-agent-instructions"'],
    ['GeneralTab', generalTab, 'id="agent-description"'],
    ['MemoryTab', memoryTab, 'projects.memory.noteLabel'],
    ['LaunchRunDialog', launchRun, 'id="launch-prompt"'],
    ['ProposalReview', proposalReview, 'id="proposal-description"'],
    ['DocSheet', docSheet, 'knowledge.sheet.descriptionLabel'],
  ])('%s: %s is dictatable', (_file, source, marker) => {
    const at = source.indexOf(marker)
    expect(at).toBeGreaterThan(0)
    const opening = source.lastIndexOf('<Textarea', at)
    const closing = source.indexOf('/>', at)
    expect(source.slice(opening, closing)).toMatch(/\n\s+dictation\b/)
  })
})
