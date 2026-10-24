import { FileCode2, Puzzle, WandSparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { type Skill, useUpdateSkill } from '@/api/skills'
import { Switch } from '@/components/ui/switch'
import { relativeTime } from '@/lib/time'
import { cn } from '@/lib/utils'

/** One skill of the library, as the design draws it (`docs/design/screens.md` §10). */
export function SkillCard({
  skill,
  onOpen,
  update = false,
  proposedBy,
}: {
  skill: Skill
  onOpen: (id: string) => void
  /** Its registry has a newer version. */
  update?: boolean
  /** A proposal waiting for the person: the agent that proposed it. */
  proposedBy?: string
}) {
  const { t } = useTranslation()
  const toggle = useUpdateSkill()
  const proposed = skill.review === 'proposed'
  return (
    <article
      className={cn(
        'flex flex-col gap-2 rounded-xl border border-sep p-3.5 shadow-card bg-card-grad',
        proposed && 'border-dashed border-violet-400/70',
        !skill.enabled && !proposed && 'opacity-60',
      )}
    >
      <div className="flex items-start gap-2.5">
        <Puzzle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <button
          type="button"
          onClick={() => onOpen(skill.id)}
          aria-label={t('skills.actions.open', { name: skill.name })}
          className="min-w-0 flex-1 text-left"
        >
          <span className="block truncate font-mono text-[13px] font-medium">{skill.name}</span>
          <span className="line-clamp-2 text-[12.5px] text-muted-foreground">
            {skill.description}
          </span>
        </button>
        {!proposed && (
          <Switch
            checked={skill.enabled}
            aria-label={t('skills.actions.enable', { name: skill.name })}
            onCheckedChange={(enabled) => toggle.mutate({ id: skill.id, enabled })}
          />
        )}
      </div>
      {proposed ? (
        <p className="text-[12px] text-violet-500">
          {t('skills.card.proposed', { agent: proposedBy ?? '' })}
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted-foreground">
          <span className="rounded bg-subtle px-1.5">{t(`skills.level.${skill.scope}`)}</span>
          {skill.origin !== 'user' && (
            <span className="rounded bg-subtle px-1.5">
              {skill.origin === 'registry'
                ? t('skills.origin.registry_short')
                : t(`skills.origin.${skill.origin}`)}
            </span>
          )}
          {skill.version !== null && (
            <span>{t('skills.card.version', { number: skill.version })}</span>
          )}
          {skill.executables > 0 && (
            <span className="flex items-center gap-1">
              <FileCode2 className="size-3" aria-hidden />
              {t('skills.card.scripts', { count: skill.executables })}
            </span>
          )}
          {!skill.model_invocable && <span>{t('skills.card.manualOnly')}</span>}
          {update && (
            <span className="rounded bg-status-running/15 px-1.5 text-status-running">
              {t('skills.card.update')}
            </span>
          )}
          <span className="ml-auto flex items-center gap-1">
            {skill.used > 0 && <WandSparkles className="size-3" aria-hidden />}
            {skill.used > 0
              ? `${t('skills.card.used', { count: skill.used })}${
                  skill.last_used
                    ? ` · ${t('skills.card.lastUsed', { when: relativeTime(skill.last_used) })}`
                    : ''
                }`
              : t('skills.card.neverUsed')}
          </span>
        </div>
      )}
    </article>
  )
}
