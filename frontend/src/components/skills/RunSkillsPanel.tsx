import { WandSparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useRunSkills } from '@/api/skills'

/** The skills a run was offered, which ones it loaded, how, and in which version (spec B). */
export function RunSkillsPanel({ runId }: { runId: string }) {
  const { t } = useTranslation()
  const rows = useRunSkills(runId).data ?? []
  return (
    <section aria-label={t('skills.run.title')} className="mt-4 flex flex-col gap-1.5">
      <h3 className="text-[12px] font-medium tracking-wide text-muted-foreground uppercase">
        {t('skills.run.title')}
      </h3>
      {rows.length === 0 ? (
        <p className="text-[12.5px] text-muted-foreground">{t('skills.run.none')}</p>
      ) : (
        <ul className="flex flex-col gap-1 text-[12.5px]">
          {rows.map((row) => (
            <li key={row.skill_id} className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono">{row.skill_name}</span>
              {row.version !== null && (
                <span className="text-muted-foreground">
                  {t('skills.run.version', { number: row.version })}
                </span>
              )}
              <span className="text-muted-foreground">
                · {t(`skills.run.offered.${row.offered}`, { rank: row.rank })}
              </span>
              {row.offered === 'candidate' && row.loaded_via && (
                <span className="flex items-center gap-1 rounded bg-status-running/15 px-1.5 text-[11px] text-status-running">
                  <WandSparkles className="size-3" aria-hidden />
                  {t('skills.run.autoselected')}
                </span>
              )}
              <span className="text-muted-foreground">
                {row.loaded_via ? t(`skills.run.via.${row.loaded_via}`) : t('skills.run.notLoaded')}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
