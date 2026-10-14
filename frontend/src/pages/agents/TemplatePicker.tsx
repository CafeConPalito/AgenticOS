import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useAgentTemplates, useCreateAgent } from '@/api/agents'
import type { AgentTemplate } from '@/api/types'
import { AgentAvatar, CliTag } from '@/components/agentic/primitives'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'

/**
 * Template cards (+ blank). By default clicking one creates the agent and opens its editor;
 * with `onPick` it only chooses (the new-agent dialog then lets the person adjust it).
 */
export function TemplatePicker({
  compact = false,
  onPick,
  selected,
}: {
  compact?: boolean
  onPick?: (template: AgentTemplate | null) => void
  /** With `onPick`: the chosen template id, or `null` for the blank one. */
  selected?: string | null
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data: templates } = useAgentTemplates()
  const create = useCreateAgent()

  async function pick(template: string | null) {
    if (onPick) {
      onPick(templates?.find((item) => item.id === template) ?? null)
      return
    }
    try {
      const agent = await create.mutateAsync(
        template ? { template } : { name: t('agents.new.blankName') },
      )
      toast.success(t('agents.new.created', { name: agent.name }))
      navigate(`/agentes/${agent.id}/general`)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <div
      className={cn(
        'grid w-full gap-3',
        compact ? 'grid-cols-4' : 'grid-cols-[repeat(auto-fill,minmax(260px,1fr))]',
      )}
    >
      {templates?.map((template) => (
        <button
          key={template.id}
          type="button"
          disabled={create.isPending}
          onClick={() => void pick(template.id)}
          aria-pressed={onPick ? selected === template.id : undefined}
          className={cn(
            'flex flex-col gap-2 rounded-lg border bg-card p-3.5 text-left hover:border-ring disabled:opacity-60',
            selected === template.id && 'border-ring bg-accent',
          )}
        >
          <div className="flex items-center gap-2.5">
            <AgentAvatar name={template.name} color={template.color} size={30} />
            <div className="min-w-0 flex-1">
              <div className="font-medium">{template.name}</div>
              <div className="text-xs text-muted-foreground">{template.role}</div>
            </div>
            <CliTag cli={template.cli} label={t(`cli.${template.cli}`)} size={20} />
          </div>
          {!compact && (
            <p className="text-xs text-pretty text-muted-foreground">{template.description}</p>
          )}
        </button>
      ))}
      <button
        type="button"
        disabled={create.isPending}
        onClick={() => void pick(null)}
        aria-pressed={onPick ? selected === null : undefined}
        className={cn(
          'flex items-center gap-2.5 rounded-lg border border-dashed border-input p-3.5 text-left hover:border-ring disabled:opacity-60',
          selected === null && 'border-ring bg-accent',
        )}
      >
        <span className="grid size-[30px] place-items-center rounded-lg bg-accent">
          <Plus className="size-4" />
        </span>
        <div>
          <div className="font-medium">{t('agents.new.blank')}</div>
          {!compact && (
            <div className="text-xs text-muted-foreground">{t('agents.new.blankDescription')}</div>
          )}
        </div>
      </button>
    </div>
  )
}
