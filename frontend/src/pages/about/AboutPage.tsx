import { isTauri } from '@tauri-apps/api/core'
import { Bug, ExternalLink, FileText, Mail, Scale } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useDataDir } from '@/api/settings'
import { BrandLogo } from '@/components/layout/BrandLogo'
import { Logo } from '@/components/layout/Logo'
import { PageContainer } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useHealth } from '@/hooks/useHealth'
import { openBackendLogs } from '@/lib/api'
import { bugReportHref, CONTACT_EMAIL } from '@/lib/bug-report'
import { cn } from '@/lib/utils'
import { Segmented } from '@/pages/usage/parts'

interface ThirdParty {
  ecosystem: 'npm' | 'python' | 'rust'
  name: string
  version: string
  license: string
  url: string
}

type Ecosystem = 'all' | ThirdParty['ecosystem']

const CARD = 'flex flex-col gap-3 rounded-xl border border-sep p-5 shadow-card bg-card-grad'

/** «Acerca de» (phase 20): who made the app, its license, how to report a bug, the system. */
export default function AboutPage() {
  const { t } = useTranslation()
  const health = useHealth().data
  const dataDir = useDataDir().data
  const a = 'about'
  const version = __APP_VERSION__
  const backendVersion = health?.version

  const mailto = bugReportHref({
    version,
    backendVersion,
    texts: {
      subject: t(`${a}.bug.subject`),
      doing: t(`${a}.bug.doing`),
      expected: t(`${a}.bug.expected`),
      happened: t(`${a}.bug.happened`),
      logs: t(`${a}.bug.logs`),
    },
  })

  return (
    <PageContainer>
      <section aria-labelledby="about-app" className={cn(CARD, 'flex-row items-center gap-4')}>
        <div className="scale-[1.6]">
          <Logo />
        </div>
        <div className="ml-2 flex min-w-0 flex-col gap-0.5">
          <h1 id="about-app" className="text-[22px] font-bold tracking-[-0.02em]">
            {t('app.name')}
          </h1>
          <p className="text-[13px] text-muted-foreground">{t(`${a}.tagline`)}</p>
          <p className="font-mono text-xs text-muted-foreground">
            {t(`${a}.version`, { version })}
            {backendVersion && backendVersion !== version
              ? ` · ${t(`${a}.backendVersion`, { version: backendVersion })}`
              : ''}
          </p>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-5 max-lg:grid-cols-1">
        <section aria-labelledby="about-authors" className={cn(CARD, 'items-center text-center')}>
          <h2 id="about-authors" className="sr-only">
            {t(`${a}.authors`)}
          </h2>
          <BrandLogo size={96} />
          <p className="text-[15px] font-medium">{t(`${a}.madeBy`)}</p>
          <p className="text-[13px] text-muted-foreground">{t(`${a}.author`)}</p>
        </section>

        <section aria-labelledby="about-help" className={CARD}>
          <h2 id="about-help" className="flex items-center gap-2 text-[15px] font-medium">
            <Bug className="size-4" />
            {t(`${a}.help.title`)}
          </h2>
          <p className="text-[13px] text-muted-foreground">{t(`${a}.help.text`)}</p>
          <div className="flex flex-wrap gap-2">
            <Button asChild className="bg-primary-action text-white hover:bg-primary-action-hover">
              <a href={mailto}>
                <Mail />
                {t(`${a}.help.report`)}
              </a>
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {t(`${a}.help.address`, { email: CONTACT_EMAIL })}
          </p>
        </section>
      </div>

      <License />

      <section aria-labelledby="about-system" className={CARD}>
        <h2 id="about-system" className="text-[15px] font-medium">
          {t(`${a}.system.title`)}
        </h2>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-[13px]">
          <dt className="text-muted-foreground">{t(`${a}.system.dataDir`)}</dt>
          <dd className="font-mono text-xs break-all">{dataDir?.path ?? '—'}</dd>
          <dt className="text-muted-foreground">{t(`${a}.system.backend`)}</dt>
          <dd className="font-mono text-xs">{health?.url ?? '—'}</dd>
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
          <p className="text-xs text-muted-foreground">{t(`${a}.system.logsHint`)}</p>
        )}
      </section>

      <ThirdParties />
    </PageContainer>
  )
}

function License() {
  const { t } = useTranslation()
  const [text, setText] = useState<string | null>(null)
  const a = 'about.license'
  return (
    <section aria-labelledby="about-license" className={CARD}>
      <h2 id="about-license" className="flex items-center gap-2 text-[15px] font-medium">
        <Scale className="size-4" />
        {t(`${a}.title`)}
      </h2>
      <p className="text-[13px] text-muted-foreground">{t(`${a}.summary`)}</p>
      <p className="text-xs text-muted-foreground">{t('about.copyright')}</p>
      <details
        onToggle={(e) => {
          // The full text (35 KB) is loaded only when asked for; it ships with the app.
          if ((e.target as HTMLDetailsElement).open && text === null)
            void import('../../../../LICENSE?raw').then((m) => setText(m.default))
        }}
      >
        <summary className="cursor-pointer text-[13px] font-medium">{t(`${a}.full`)}</summary>
        <pre className="mt-3 max-h-[420px] overflow-auto rounded-lg border border-sep bg-subtle p-4 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap">
          {text ?? t(`${a}.loading`)}
        </pre>
      </details>
    </section>
  )
}

function ThirdParties() {
  const { t } = useTranslation()
  const [packages, setPackages] = useState<ThirdParty[] | null>(null)
  const [query, setQuery] = useState('')
  const [ecosystem, setEcosystem] = useState<Ecosystem>('all')
  const a = 'about.thirdParty'

  useEffect(() => {
    let alive = true
    void import('@/generated/third-party-licenses.json').then((m) => {
      if (alive) setPackages(m.default.packages as ThirdParty[])
    })
    return () => {
      alive = false
    }
  }, [])

  const shown = useMemo(() => {
    const words = query.trim().toLowerCase()
    return (packages ?? []).filter(
      (p) =>
        (ecosystem === 'all' || p.ecosystem === ecosystem) &&
        (!words || `${p.name} ${p.license}`.toLowerCase().includes(words)),
    )
  }, [packages, query, ecosystem])

  return (
    <section aria-labelledby="about-third" className={CARD}>
      <h2 id="about-third" className="text-[15px] font-medium">
        {t(`${a}.title`)}
      </h2>
      <p className="text-[13px] text-muted-foreground">{t(`${a}.text`)}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Input
          aria-label={t(`${a}.search`)}
          placeholder={t(`${a}.search`)}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="h-8 max-w-[280px]"
        />
        <Segmented<Ecosystem>
          label={t(`${a}.ecosystem`)}
          value={ecosystem}
          onChange={setEcosystem}
          options={(['all', 'npm', 'python', 'rust'] as const).map((value) => ({
            value,
            label: t(`${a}.ecosystems.${value}`),
          }))}
        />
        <span className="text-xs text-muted-foreground">
          {t(`${a}.count`, { count: shown.length })}
        </span>
      </div>
      <div className="max-h-[420px] overflow-auto rounded-lg border border-sep">
        <table className="w-full text-[12.5px]">
          <thead className="sticky top-0 bg-subtle text-left text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">{t(`${a}.name`)}</th>
              <th className="px-3 py-2 font-medium">{t(`${a}.version`)}</th>
              <th className="px-3 py-2 font-medium">{t(`${a}.license`)}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((p) => (
              <tr key={`${p.ecosystem}/${p.name}/${p.version}`} className="border-t border-sep">
                <td className="px-3 py-1.5">
                  {p.url ? (
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 hover:underline"
                    >
                      {p.name}
                      <ExternalLink className="size-3 text-muted-foreground" />
                    </a>
                  ) : (
                    p.name
                  )}
                </td>
                <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground">{p.version}</td>
                <td className="px-3 py-1.5">{p.license}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">{t(`${a}.own`)}</p>
    </section>
  )
}
