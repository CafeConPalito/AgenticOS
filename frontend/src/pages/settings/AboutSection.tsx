import { isTauri } from '@tauri-apps/api/core'
import { FileText, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useDataDir } from '@/api/settings'
import { Button } from '@/components/ui/button'
import { useHealth } from '@/hooks/useHealth'
import { openBackendLogs } from '@/lib/api'

/** «Acerca de» (phase 08): version, where the data and the logs are. */
export function AboutSection() {
  const { t } = useTranslation()
  const health = useHealth().data
  const dataDir = useDataDir().data
  const rows: [string, React.ReactNode][] = [
    [t('settings.about.version'), <span className="font-mono">{health?.version ?? '—'}</span>],
    [
      t('settings.about.dataDir'),
      <span className="font-mono text-xs break-all">{dataDir?.path ?? '—'}</span>,
    ],
    [t('settings.about.backend'), <span className="font-mono text-xs">{health?.url ?? '—'}</span>],
  ]
  return (
    <section
      aria-labelledby="about-title"
      className="flex flex-col gap-3 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <h2 id="about-title" className="flex items-center gap-2 text-[15px] font-medium">
        <Info className="size-4" />
        {t('settings.about.title')}
      </h2>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-[13px]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="min-w-0">{value}</dd>
          </div>
        ))}
      </dl>
      {isTauri() ? (
        <div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void openBackendLogs().catch((error) => toast.error(String(error)))}
          >
            <FileText />
            {t('backend.openLogs')}
          </Button>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">{t('settings.about.logsHint')}</p>
      )}
    </section>
  )
}
