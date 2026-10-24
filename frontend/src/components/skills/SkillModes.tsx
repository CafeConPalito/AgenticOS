import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type SkillMode,
  useAgentSkillModes,
  useCliSkills,
  useSetSkillModes,
  useStageSkillModes,
} from '@/api/skills'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/form-errors'

const MODES: SkillMode[] = ['auto', 'always', 'never']

/**
 * Automatic / always / never for every skill an agent or a stage can see (spec B). On a stage,
 * «Automática» means «what the agent says», shown next to it: the stage wins over the agent.
 */
export function SkillModes(props: { agentId: string; agentCli?: string } | { stageId: string }) {
  const { t } = useTranslation()
  const agent = 'agentId' in props
  const agentModes = useAgentSkillModes(agent ? props.agentId : '')
  const stageModes = useStageSkillModes(agent ? null : props.stageId)
  const rows = agent ? agentModes : stageModes
  const save = useSetSkillModes(agent ? { agentId: props.agentId } : { stageId: props.stageId })
  const agy = agent && props.agentCli === 'agy'
  const scan = useCliSkills(agy)
  const globals = (scan.data ?? []).filter((s) => s.source === 'agy_global').length

  if (rows.isPending) return <Skeleton aria-busy className="h-20 rounded-lg" />
  return (
    <section aria-label={t('skills.modes.title')} className="flex flex-col gap-2">
      <h3 className="text-[14px] font-medium">{t('skills.modes.title')}</h3>
      <p className="text-[12.5px] text-muted-foreground">
        {t(agent ? 'skills.modes.agentHint' : 'skills.modes.stageHint')}
      </p>
      {agy && globals > 0 && (
        <p role="note" className="text-[12.5px] text-status-waiting">
          {t('skills.modes.agyGlobal', { count: globals })}
        </p>
      )}
      {(rows.data ?? []).length === 0 ? (
        <p className="text-[13px] text-muted-foreground">{t('skills.modes.none')}</p>
      ) : (
        <ul className="overflow-hidden rounded-lg border border-sep">
          {(rows.data ?? []).map((row) => (
            <li
              key={row.skill.id}
              className="flex items-center gap-3 border-b border-sep px-3 py-1.5 last:border-b-0"
            >
              <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]">
                {row.skill.name}
              </span>
              {!agent && row.mode === 'auto' && row.set_by === 'agent' && (
                <span className="text-[11.5px] text-muted-foreground">
                  {t('skills.modes.inherit', { mode: t(`skills.modes.${row.effective}`) })}
                </span>
              )}
              <Select
                value={row.mode}
                onValueChange={(mode) =>
                  save.mutate(
                    { [row.skill.id]: mode as SkillMode },
                    {
                      onSuccess: () => toast.success(t('skills.modes.saved')),
                      onError: (error) => toast.error(errorMessage(error)),
                    },
                  )
                }
              >
                <SelectTrigger
                  aria-label={t('skills.modes.label', { name: row.skill.name })}
                  className="h-7 w-[130px]"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODES.map((mode) => (
                    <SelectItem key={mode} value={mode}>
                      {t(`skills.modes.${mode}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
