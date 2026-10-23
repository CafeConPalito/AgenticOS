import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useCreateAgent } from '@/api/agents'
import { useClis } from '@/api/clis'
import type { AgentTemplate, CliId, PermissionMode } from '@/api/types'
import { PERMISSION_MODES } from '@/api/types'
import { Field } from '@/components/page'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { NewAgentInit } from '@/stores/dialogs'
import i18n from '@/i18n'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import { AccountSelect, FallbackFields, TeamSelect } from './AgentLinks'
import { TemplatePicker } from './TemplatePicker'

const CLIS: CliId[] = ['claude', 'agy']
const DEFAULT_MODEL = '__default__' // Radix Select cannot use "" as an item value
const BLANK_COLOR = '#8FB4FF'

interface Draft {
  template: string | null
  name: string
  role: string
  cli: CliId
  model: string
  permission_mode: PermissionMode
  instructions: string
  color: string
  team_id: string | null
  account_id: string | null
  fallback_account_id: string | null
  fallback_model: string
}

const BLANK: Draft = {
  template: null,
  name: '',
  role: '',
  cli: 'claude',
  model: '',
  permission_mode: 'ask',
  instructions: '',
  color: BLANK_COLOR,
  team_id: null,
  account_id: null,
  fallback_account_id: null,
  fallback_model: '',
}

/** Creates an agent as a draft (activated later from its page): from a template or blank. */
export function NewAgentDialog({
  open,
  onOpenChange,
  init,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** From a team's «+ Agente»: the team is preselected. */
  init?: NewAgentInit | null
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <NewAgentForm onClose={() => onOpenChange(false)} init={init ?? {}} />}
    </Dialog>
  )
}

function NewAgentForm({ onClose, init }: { onClose: () => void; init: NewAgentInit }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const create = useCreateAgent()
  const { data: clis } = useClis()
  const [draft, setDraft] = useState<Draft>({ ...BLANK, team_id: init.teamId ?? null })
  const [error, setError] = useState<string | null>(null)
  const models = clis?.find((c) => c.id === draft.cli)?.models ?? []
  const modelLabel = (m: { id: string; label: string | null }) => {
    if (m.label) return m.label
    const key = `cli.alias.${m.id}`
    return i18n.exists(key) ? t(key as never) : m.id
  }
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))

  function pick(template: AgentTemplate | null) {
    // The team the person is creating the agent for survives choosing a template.
    setDraft((d) =>
      template
        ? {
            template: template.id,
            name: template.name,
            role: template.role,
            cli: template.cli,
            model: template.model,
            permission_mode: template.permission_mode,
            instructions: template.instructions,
            color: template.color,
            team_id: d.team_id,
            account_id: null,
            fallback_account_id: null,
            fallback_model: '',
          }
        : { ...BLANK, team_id: d.team_id },
    )
  }

  async function submit() {
    if (!draft.name.trim()) return
    setError(null)
    try {
      const agent = await create.mutateAsync({
        ...(draft.template && { template: draft.template }),
        name: draft.name.trim(),
        role: draft.role.trim(),
        cli: draft.cli,
        model: draft.model,
        permission_mode: draft.permission_mode,
        instructions: draft.instructions,
        color: draft.color,
        team_id: draft.team_id,
        account_id: draft.account_id,
        fallback_account_id: draft.fallback_account_id,
        fallback_model: draft.fallback_model,
        status: 'draft',
      })
      toast.success(t('agents.new.created', { name: agent.name }))
      onClose()
      void navigate(`/agentes/${agent.id}`)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <DialogContent className="max-h-[calc(100vh-48px)] gap-0 overflow-y-auto p-0 sm:max-w-[760px]">
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          e.stopPropagation()
          void submit()
        }}
        className="flex flex-col"
      >
        <DialogHeader className="border-b border-sep px-5 py-4">
          <DialogTitle className="text-[15px] font-medium">{t('agents.new.title')}</DialogTitle>
          <DialogDescription>{t('agents.new.subtitle')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 p-5">
          <TemplatePicker compact onPick={pick} selected={draft.template} />

          <div className="grid grid-cols-2 gap-3">
            <Field label={t('agents.fields.name')} htmlFor="new-agent-name">
              <Input
                id="new-agent-name"
                value={draft.name}
                maxLength={80}
                onChange={(e) => set('name', e.target.value)}
              />
            </Field>
            <Field label={t('agents.fields.role')} htmlFor="new-agent-role">
              <Input
                id="new-agent-role"
                value={draft.role}
                maxLength={80}
                onChange={(e) => set('role', e.target.value)}
              />
            </Field>
            <Field label={t('agents.fields.cli')} htmlFor="new-agent-cli">
              <Select
                value={draft.cli}
                onValueChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    cli: v as CliId,
                    model: '',
                    account_id: null,
                    fallback_account_id: null,
                    fallback_model: '',
                  }))
                }
              >
                <SelectTrigger id="new-agent-cli" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CLIS.map((id) => (
                    <SelectItem key={id} value={id}>
                      {t(`cli.${id}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label={t('agents.fields.team')} htmlFor="new-agent-team">
              <TeamSelect
                id="new-agent-team"
                value={draft.team_id}
                onChange={(teamId) => set('team_id', teamId)}
              />
            </Field>
            <Field label={t('agents.fields.account')} htmlFor="new-agent-account">
              <AccountSelect
                id="new-agent-account"
                cli={draft.cli}
                value={draft.account_id}
                onChange={(accountId) => set('account_id', accountId)}
              />
            </Field>
            <Field label={t('agents.fields.model')} htmlFor="new-agent-model">
              <Select
                value={draft.model || DEFAULT_MODEL}
                onValueChange={(v) => set('model', v === DEFAULT_MODEL ? '' : v)}
              >
                <SelectTrigger id="new-agent-model" className="w-full font-mono text-[12.5px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={DEFAULT_MODEL}>{t('cli.defaultModel')}</SelectItem>
                  {draft.model && !models.some((m) => m.id === draft.model) && (
                    <SelectItem value={draft.model}>{draft.model}</SelectItem>
                  )}
                  {models.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      <span className="font-mono">{m.id}</span>
                      <span className="text-muted-foreground"> · {modelLabel(m)}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>

          <FallbackFields
            idPrefix="new-agent"
            cli={draft.cli}
            accountId={draft.account_id}
            fallbackAccountId={draft.fallback_account_id}
            fallbackModel={draft.fallback_model}
            onChange={(value) => setDraft((d) => ({ ...d, ...value }))}
          />

          <Field label={t('agents.fields.permissions')}>
            <div
              role="radiogroup"
              aria-label={t('agents.fields.permissions')}
              className="flex rounded-lg border bg-subtle p-0.5"
            >
              {PERMISSION_MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={draft.permission_mode === mode}
                  title={t(`agents.permission.${mode}Help`)}
                  onClick={() => set('permission_mode', mode)}
                  className={cn(
                    'flex-1 rounded-md px-3 py-1.5 text-[13px] text-muted-foreground',
                    draft.permission_mode === mode &&
                      'bg-card font-medium text-foreground shadow-sm',
                  )}
                >
                  {t(`agents.permission.${mode}`)}
                </button>
              ))}
            </div>
          </Field>

          <Field label={t('agents.fields.instructions')} htmlFor="new-agent-instructions">
            <Textarea
              id="new-agent-instructions"
              dictation
              value={draft.instructions}
              onChange={(e) => set('instructions', e.target.value)}
              className="min-h-[110px]"
            />
          </Field>

          {error && (
            <p role="alert" className="text-sm text-status-failed">
              {error}
            </p>
          )}
        </div>

        <DialogFooter className="gap-2 border-t border-sep px-5 py-3">
          <span className="mr-auto self-center text-xs text-muted-foreground">
            {t('agents.new.draftNote')}
          </span>
          <Button type="button" variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            disabled={!draft.name.trim() || create.isPending}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {create.isPending ? t('common.creating') : t('agents.new.submit')}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}
