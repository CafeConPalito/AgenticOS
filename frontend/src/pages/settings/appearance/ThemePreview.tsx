import { Play, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { AgentAvatar, StatusBadge } from '@/components/agentic/primitives'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DEFAULT_AGENT_COLOR, DRAFT_AGENT_COLOR } from '@/theme/palettes'

/**
 * A sample of the app with the real components, under the theme being edited (the editor
 * shows it on the whole app while it is open, so this is the place to look).
 */
export function ThemePreview() {
  const { t } = useTranslation()
  const p = 'appearance.preview'
  return (
    <div
      aria-label={t(`${p}.title`)}
      role="region"
      className="flex flex-col gap-3 rounded-xl border border-sep p-4 shadow-card bg-atmos"
    >
      <div className="flex items-center gap-2 rounded-full px-3 py-2 glass">
        <span className="text-[13px] font-bold">{t('app.name')}</span>
        <span className="ml-auto rounded-full bg-accent px-2.5 py-1 text-[12px]">
          {t('nav.board')}
        </span>
        <span className="px-2.5 py-1 text-[12px] text-muted-foreground">{t('nav.runs')}</span>
      </div>
      <div className="flex flex-col gap-2 rounded-xl border border-sep p-3 shadow-card bg-card-grad">
        <div className="flex items-center gap-2">
          <AgentAvatar name="Dev" color={DEFAULT_AGENT_COLOR} size={28} />
          <span className="text-[14px] font-medium">{t(`${p}.agent`)}</span>
          <span className="ml-auto">
            <StatusBadge tone="running" label={t(`${p}.running`)} size="xs" />
          </span>
        </div>
        <p className="text-[12.5px] text-muted-foreground">{t(`${p}.description`)}</p>
        <div className="flex flex-wrap gap-1.5">
          <StatusBadge tone="queued" label={t(`${p}.queued`)} size="xs" />
          <StatusBadge tone="waiting" label={t(`${p}.waiting`)} size="xs" />
          <StatusBadge tone="review" label={t(`${p}.review`)} size="xs" />
          <StatusBadge tone="done" label={t(`${p}.done`)} size="xs" />
          <StatusBadge tone="failed" label={t(`${p}.failed`)} size="xs" />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button className="rounded-full bg-primary-action text-white hover:bg-primary-action-hover">
          <Plus />
          {t(`${p}.primary`)}
        </Button>
        <Button variant="outline" className="rounded-full">
          <Play />
          {t(`${p}.secondary`)}
        </Button>
        <Button variant="destructive">{t(`${p}.destructive`)}</Button>
        <Input readOnly value={t(`${p}.input`)} className="max-w-[180px]" />
        <AgentAvatar name="Arquitecto" color={DRAFT_AGENT_COLOR} size={24} />
      </div>
      <div className="overflow-hidden rounded-lg border border-terminal-border font-mono text-[12px]">
        <div className="bg-[var(--diff-add-bg)] px-3 py-0.5 text-[var(--diff-add-fg)]">
          + {t(`${p}.added`)}
        </div>
        <div className="bg-[var(--diff-del-bg)] px-3 py-0.5 text-[var(--diff-del-fg)]">
          − {t(`${p}.removed`)}
        </div>
        <div className="bg-terminal px-3 py-2 text-terminal-foreground">
          <span className="text-[var(--ansi-green)]">$</span> {t(`${p}.command`)}{' '}
          <span className="text-[var(--ansi-cyan)]">{t(`${p}.task`)}</span>
          <span className="ml-1 inline-block h-3.5 w-2 animate-blink bg-[var(--terminal-cursor)] align-middle" />
          <div className="text-terminal-muted">{t(`${p}.terminal`)}</div>
        </div>
      </div>
    </div>
  )
}
