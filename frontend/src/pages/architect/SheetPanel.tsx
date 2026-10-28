import { AlertTriangle, Check, Lock, Pencil, Sparkles, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { type Conversation, type SheetAgent, useConversationActions } from '@/api/architect'
import { AgentAvatar } from '@/components/agentic/primitives'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import { TeamSheet } from './TeamSheet'
import { DRAFT_AGENT_COLOR } from '@/theme/palettes'

const REF = 'main'
type TextField = 'name' | 'role' | 'description' | 'instructions'

/** The sheet the Architect fills while it talks (design §11, right half): every field as it is
 * now, empty ones as a dashed skeleton, the person's own edits locked for the Architect. */
export function SheetPanel({ conversation }: { conversation: Conversation }) {
  if (
    conversation.mode === 'team' ||
    conversation.mode === 'improve_team' ||
    conversation.mode === 'improve_pipeline'
  )
    return <TeamSheet conversation={conversation} />
  return <AgentSheet conversation={conversation} />
}

function AgentSheet({ conversation }: { conversation: Conversation }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const actions = useConversationActions(conversation.id)
  const { sheet, issues, progress, ready, locked } = conversation.sheet
  const agent: SheetAgent = sheet.agents[REF] ?? {}
  const percent = progress[REF] ?? 0
  const improving = conversation.mode === 'improve_agent'
  const isLocked = (field: string) => locked.includes(`${REF}.${field}`)
  // Improving an agent: what differs from the agent as it is.
  const base = ((sheet.base?.agents as Record<string, SheetAgent> | undefined) ?? {})[REF]
  const differs = (...fields: (keyof SheetAgent)[]) =>
    !!base &&
    fields.some((f) => JSON.stringify(agent[f] ?? null) !== JSON.stringify(base[f] ?? null))

  async function save(field: TextField, value: string) {
    try {
      const answer = await actions.patchSheet.mutateAsync({ patch: { [field]: value } })
      const refused = answer.refused?.[`${REF}.${field}`]
      if (refused) toast.error(refused)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function propose() {
    try {
      const proposal = await actions.propose.mutateAsync()
      toast.success(t(improving ? 'architect.proposed' : 'architect.drafted'))
      if (proposal.target_agent_id) navigate(`/agentes/${proposal.target_agent_id}/resumen`)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const unlock = (field: string) => actions.unlock.mutate([`${REF}.${field}`])
  const errors = issues.filter((i) => i.level === 'error')
  const warnings = issues.filter((i) => i.level === 'warning')

  return (
    <aside className="flex min-h-0 flex-col bg-subtle" aria-label={t('architect.sheet')}>
      <div className="border-b border-sep px-5 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-medium">
            {t(improving ? 'architect.sheetImprove' : 'architect.sheet')}
          </h2>
          <span className="text-[12.5px] text-muted-foreground">
            {t('architect.progress', { percent })}
          </span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
          <div
            className="h-full rounded-full transition-[width]"
            style={{ width: `${percent}%`, background: 'var(--status-review)' }}
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
        <div className="space-y-4 rounded-lg border border-sep bg-card p-4">
          <Row
            label={t('architect.fields.identity')}
            empty={!agent.name && !agent.role}
            changed={differs('name', 'role')}
          >
            <div className="flex items-center gap-3">
              <AgentAvatar
                name={agent.name || '?'}
                color={agent.color || DRAFT_AGENT_COLOR}
                avatar={agent.avatar ?? null}
                size={36}
              />
              <div className="min-w-0 flex-1 space-y-1">
                <Editable
                  value={agent.name ?? ''}
                  label={t('architect.fields.name')}
                  locked={isLocked('name')}
                  onUnlock={() => unlock('name')}
                  onSave={(v) => save('name', v)}
                  className="font-medium"
                />
                <Editable
                  value={agent.role ?? ''}
                  label={t('architect.fields.role')}
                  locked={isLocked('role')}
                  onUnlock={() => unlock('role')}
                  onSave={(v) => save('role', v)}
                  className="text-muted-foreground"
                />
              </div>
            </div>
          </Row>
          <Row
            label={t('architect.fields.description')}
            empty={!agent.description}
            changed={differs('description')}
          >
            <Editable
              value={agent.description ?? ''}
              label={t('architect.fields.description')}
              locked={isLocked('description')}
              onUnlock={() => unlock('description')}
              onSave={(v) => save('description', v)}
              multiline
            />
          </Row>
          <Row
            label={t('architect.fields.execution')}
            empty={!agent.cli}
            changed={differs('cli', 'model', 'account', 'permission_mode', 'allowed_tools')}
          >
            <p>
              <span className="font-medium">{agent.cli ? t(`cli.${agent.cli}`) : ''}</span>
              {agent.model && <span className="ml-2 font-mono text-[12.5px]">{agent.model}</span>}
            </p>
            {agent.permission_mode && (
              <p className="text-[12.5px] text-muted-foreground">
                {t(`agents.permission.${agent.permission_mode}`)}
                {agent.allowed_tools?.length
                  ? ` · ${agent.allowed_tools.map((x) => t(`agents.tool.${x}`)).join(', ')}`
                  : ''}
              </p>
            )}
          </Row>
          <Row
            label={t('architect.fields.skills')}
            empty={agent.skills === undefined && !agent.new_skills}
            changed={differs('skills', 'new_skills')}
          >
            <Chips
              items={[
                ...(agent.skills ?? []).map((s) => `${s.name} · ${t(`skills.modes.${s.mode}`)}`),
                ...(agent.new_skills ?? []).map((s) => `${s.name} · ${t('architect.newSkill')}`),
              ]}
              none={t('architect.none')}
            />
          </Row>
          <Row
            label={t('architect.fields.knowledge')}
            empty={agent.knowledge === undefined}
            changed={differs('knowledge')}
          >
            <Chips
              items={(agent.knowledge ?? []).map((d) => d.title)}
              none={t('architect.none')}
              mono
            />
          </Row>
          <Row
            label={t('architect.fields.connections')}
            empty={agent.connections === undefined}
            changed={differs('connections')}
          >
            <Chips
              items={(agent.connections ?? []).map((c) => c.name)}
              none={t('architect.none')}
            />
            {sheet.suggested_connections.length > 0 && (
              <ul className="mt-2 space-y-1 text-[12.5px]">
                {sheet.suggested_connections.map((s) => (
                  <li key={s.registry_ref} className="flex gap-1.5">
                    <Sparkles className="mt-0.5 size-3.5 shrink-0 text-status-review" aria-hidden />
                    <span>
                      {t('architect.suggested', { name: s.ref })}
                      {s.reason && <span className="text-muted-foreground"> — {s.reason}</span>}
                    </span>
                  </li>
                ))}
                <li>
                  <Link to="/conexiones?vista=explorar" className="text-[12.5px] underline">
                    {t('architect.installSuggested')}
                  </Link>
                </li>
              </ul>
            )}
          </Row>
          <Row
            label={t('architect.fields.instructions')}
            empty={!agent.instructions}
            changed={differs('instructions')}
          >
            <Editable
              value={agent.instructions ?? ''}
              label={t('architect.fields.instructions')}
              locked={isLocked('instructions')}
              onUnlock={() => unlock('instructions')}
              onSave={(v) => save('instructions', v)}
              multiline
              mono
            />
          </Row>
        </div>

        {(errors.length > 0 || warnings.length > 0) && (
          <ul className="space-y-1 text-[12.5px]" aria-label={t('architect.issues')}>
            {[...errors, ...warnings].map((issue) => (
              <li key={`${issue.field}-${issue.code}`} className="flex gap-1.5">
                <AlertTriangle
                  className={cn(
                    'mt-0.5 size-3.5 shrink-0',
                    issue.level === 'error' ? 'text-status-failed' : 'text-status-waiting',
                  )}
                  aria-hidden
                />
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-sep px-5 py-3">
        {conversation.status === 'open' ? (
          <Button
            onClick={() => void propose()}
            disabled={!ready || actions.propose.isPending}
            className="w-full bg-primary-action text-white hover:bg-primary-action-hover disabled:opacity-45"
          >
            {t(improving ? 'architect.propose' : 'architect.draft')}
          </Button>
        ) : (
          <p className="text-center text-[12.5px] text-muted-foreground">
            {t(`architect.done.${conversation.status}`)}{' '}
            {conversation.proposal_id && conversation.agent_id && (
              <Link to={`/agentes/${conversation.agent_id}/resumen`} className="underline">
                {t('architect.openAgent')}
              </Link>
            )}
          </p>
        )}
        <p className="mt-1.5 text-center text-[11.5px] text-muted-foreground">
          {t(improving ? 'architect.proposeNote' : 'architect.draftNote')}
        </p>
      </div>
    </aside>
  )
}

function Row({
  label,
  empty,
  changed = false,
  children,
}: {
  label: string
  empty: boolean
  changed?: boolean
  children: React.ReactNode
}) {
  const { t } = useTranslation()
  return (
    <section>
      <h3 className="mb-1 flex items-center gap-1.5 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">
        {label}
        {changed && (
          <span className="rounded-full px-1.5 text-[10.5px] tracking-normal text-status-review normal-case ring-1 ring-status-review">
            {t('architect.changes')}
          </span>
        )}
      </h3>
      {empty ? (
        <div
          aria-hidden
          className="h-8 animate-pulse rounded-md border border-dashed border-sep bg-muted/40"
        />
      ) : (
        children
      )}
    </section>
  )
}

function Chips({ items, none, mono = false }: { items: string[]; none: string; mono?: boolean }) {
  if (items.length === 0) return <p className="text-[12.5px] text-muted-foreground">{none}</p>
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li
          key={item}
          className={cn(
            'rounded-full border border-sep px-2 py-0.5 text-[12px]',
            mono && 'font-mono',
          )}
        >
          {item}
        </li>
      ))}
    </ul>
  )
}

/** A text field of the sheet the person can edit (and so lock for the Architect). */
function Editable({
  value,
  label,
  locked,
  onUnlock,
  onSave,
  multiline = false,
  mono = false,
  className,
}: {
  value: string
  label: string
  locked: boolean
  onUnlock: () => void
  onSave: (value: string) => Promise<void>
  multiline?: boolean
  mono?: boolean
  className?: string
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState<string | null>(null)
  if (editing !== null) {
    const Field = multiline ? Textarea : Input
    return (
      <form
        className="flex items-start gap-1"
        onSubmit={(event) => {
          event.preventDefault()
          void onSave(editing).then(() => setEditing(null))
        }}
      >
        <Field
          aria-label={label}
          value={editing}
          onChange={(event: React.ChangeEvent<HTMLInputElement & HTMLTextAreaElement>) =>
            setEditing(event.target.value)
          }
          className={cn(mono && 'font-mono text-[12.5px]', multiline && 'min-h-32')}
        />
        <Button type="submit" variant="ghost" size="icon" aria-label={t('common.save')}>
          <Check />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t('common.cancel')}
          onClick={() => setEditing(null)}
        >
          <X />
        </Button>
      </form>
    )
  }
  return (
    <div className="group flex items-start gap-1">
      {mono ? (
        <pre
          className={cn(
            'max-h-64 min-w-0 flex-1 overflow-auto font-mono text-[12px] whitespace-pre-wrap',
            className,
          )}
        >
          {value}
        </pre>
      ) : (
        <p className={cn('min-w-0 flex-1 whitespace-pre-wrap', className)}>{value}</p>
      )}
      {locked && (
        <Button
          variant="ghost"
          size="icon"
          className="size-6"
          aria-label={t('architect.unlock', { field: label })}
          title={t('architect.lockedHint')}
          onClick={onUnlock}
        >
          <Lock className="size-3.5" />
        </Button>
      )}
      <Button
        variant="ghost"
        size="icon"
        className="size-6 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
        aria-label={t('architect.edit', { field: label })}
        onClick={() => setEditing(value)}
      >
        <Pencil className="size-3.5" />
      </Button>
    </div>
  )
}
