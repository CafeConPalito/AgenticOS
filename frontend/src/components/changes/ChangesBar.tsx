import { useTranslation } from 'react-i18next'
import { type ChangesTarget, useChanges } from '@/api/changes'
import { ChangesButton } from './ChangesSheet'

/**
 * The «Cambios» entry of the task and the run pages: a button with the +/- of what changed, which
 * opens the diff in a side panel. Without a diff (no git, an old run, nothing changed) it takes
 * no room.
 */
export function ChangesBar({ target, title }: { target: ChangesTarget; title: string }) {
  const { t } = useTranslation()
  const changes = useChanges(target)
  const data = changes.data
  if (!data || data.state !== 'ok' || data.totals.files === 0) return null
  return (
    <div className="flex items-center gap-2 px-0.5">
      <span className="text-[12.5px] text-muted-foreground">{t('changes.title')}</span>
      <ChangesButton target={target} title={title} totals={data.totals} />
    </div>
  )
}
