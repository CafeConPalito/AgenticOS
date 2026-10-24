import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Proposal } from '@/api/skills'
import es from '@/i18n/es.json'
import { createFakeBackend, makeInboxItem } from '@/test/fake-backend'
import { makeSkill, makeVersion, skillFile } from '@/test/fake-skills'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const p = es.skills.proposal

function proposal(): Proposal {
  return {
    skill: makeSkill({
      id: 'new',
      name: 'migraciones-alembic',
      review: 'proposed',
      scope: 'agent',
      agent_id: 'a1',
    }),
    version: makeVersion({
      id: 'pv1',
      note: 'Lo aprendí en T-12',
      author: {
        kind: 'agent',
        label: 'Dev',
        agent_id: 'a1',
        run_id: 'r1',
        task_id: 't1',
        task_title: 'Añadir teléfono',
      },
    }),
    new_skill: true,
    suggested_scope: 'general',
    body: '# Migraciones\n1. autogenerate',
    header: { name: 'migraciones-alembic', description: 'Migraciones de Alembic.' },
    files: [skillFile('SKILL.md'), skillFile('scripts/check.py', true)],
    executables: ['scripts/check.py'],
    inbox_item_id: 'i1',
  }
}

describe('Reviewing a skill an agent proposed (CA9, CA13)', () => {
  it('opens from the Inbox and cannot be approved until its scripts are opened', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      inbox: [
        makeInboxItem({
          id: 'i1',
          kind: 'skill',
          title: 'Skill propuesta: migraciones-alembic',
          skill_version_id: 'pv1',
        }),
      ],
      skills: { proposals: [proposal()], fileTexts: { 'new/scripts/check.py': 'print(1)' } },
    })
    const user = userEvent.setup()
    renderApp('/inbox')
    await user.click(await screen.findByRole('button', { name: es.inbox.reviewSkill }))
    expect(await screen.findByText(/Propuesta por Dev en «Añadir teléfono»/)).toBeVisible()
    expect(screen.getByText(p.scripts)).toBeVisible()
    const approve = screen.getByRole('button', { name: p.approve })
    expect(approve).toBeDisabled()
    expect(screen.getByText(/Faltan por abrir: scripts\/check\.py/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Abrir scripts/check.py' }))
    expect(await screen.findByText('print(1)')).toBeVisible()
    await waitFor(() => expect(approve).toBeEnabled())
    await user.click(approve)
    await waitFor(() => expect(backend.skills.accepted).toHaveLength(1))
    expect(backend.skills.accepted[0].body).toMatchObject({
      opened_files: ['scripts/check.py'],
      scope: 'general', // the agent's suggestion, kept by default
    })
  })

  it('rejects with a reason', async () => {
    installFakeWebSocket()
    const general = proposal()
    general.skill = { ...general.skill, scope: 'general', agent_id: null }
    const backend = createFakeBackend({ skills: { proposals: [general] } })
    const user = userEvent.setup()
    renderApp('/conocimiento?vista=skills')
    await user.click(await screen.findByRole('button', { name: 'Abrir migraciones-alembic' }))
    await user.click(await screen.findByRole('button', { name: p.reject }))
    await user.type(screen.getByRole('textbox', { name: p.reason }), 'No hace falta')
    await user.click(screen.getAllByRole('button', { name: p.reject }).at(-1)!)
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/skills/proposals/pv1/reject')[0]?.body).toEqual({
        reason: 'No hace falta',
      }),
    )
  })
})

describe('Regressions of the code review', () => {
  it('approves a project-level proposal without an agent', async () => {
    installFakeWebSocket()
    const project = proposal()
    project.skill = { ...project.skill, scope: 'project', project_id: 'p1', agent_id: null }
    project.suggested_scope = 'project'
    project.executables = []
    project.files = [skillFile('SKILL.md')]
    const backend = createFakeBackend({
      inbox: [makeInboxItem({ id: 'i1', kind: 'skill', skill_version_id: 'pv1' })],
      skills: { proposals: [project] },
    })
    const user = userEvent.setup()
    renderApp('/inbox')
    await user.click(await screen.findByRole('button', { name: es.inbox.reviewSkill }))
    await user.click(await screen.findByRole('button', { name: p.approve }))
    await waitFor(() => expect(backend.skills.accepted).toHaveLength(1))
    expect(backend.skills.accepted[0].body).toMatchObject({
      scope: 'project',
      project_id: 'p1',
      agent_id: null,
    })
  })

  it('encodes file paths segment by segment', async () => {
    const { encodePath } = await import('@/api/skills')
    expect(encodePath('scripts/run#1.py')).toBe('scripts/run%231.py')
    expect(encodePath('docs/a?b.md')).toBe('docs/a%3Fb.md')
  })
})
