import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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
    ['src/pages/tasks/NewTaskDialog.tsx', 'id="task-description"'],
    ['src/pages/tasks/TaskPage.tsx', 'id="complete-summary"'],
    ['src/pages/tasks/TaskPage.tsx', 'id="reject-reason"'],
    ['src/pages/agents/NewAgentDialog.tsx', 'id="new-agent-instructions"'],
    ['src/pages/agents/tabs/GeneralTab.tsx', 'id="agent-description"'],
    ['src/pages/projects/tabs/MemoryTab.tsx', 'projects.memory.noteLabel'],
    ['src/pages/runs/LaunchRunDialog.tsx', 'id="launch-prompt"'],
    ['src/components/knowledge/ProposalReview.tsx', 'id="proposal-description"'],
    ['src/components/knowledge/DocSheet.tsx', 'knowledge.sheet.descriptionLabel'],
  ])('%s: %s is dictatable', (file, marker) => {
    const source = readFileSync(resolve(process.cwd(), file), 'utf-8')
    const at = source.indexOf(marker)
    expect(at).toBeGreaterThan(0)
    const opening = source.lastIndexOf('<Textarea', at)
    const closing = source.indexOf('/>', at)
    expect(source.slice(opening, closing)).toMatch(/\n\s+dictation\b/)
  })
})
