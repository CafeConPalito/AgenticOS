import { TerminalSquare } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { useClis } from '@/api/clis'
import { Button } from '@/components/ui/button'

/**
 * First start on a machine without agent CLIs (phase 08): nothing can run until one is
 * installed and logged in, so say so and point to Ajustes › CLIs detectados.
 */
export function CliReadinessBanner() {
  const { t } = useTranslation()
  const { data: clis } = useClis()
  if (!clis || clis.some((cli) => cli.installed && cli.logged_in !== false)) return null
  const installed = clis.some((cli) => cli.installed)
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 rounded-xl border border-status-waiting/40 bg-status-waiting/10 px-4 py-3 text-[13px]"
    >
      <TerminalSquare className="size-4 shrink-0 text-status-waiting" />
      <span className="flex-1">
        <strong className="font-medium">
          {t(installed ? 'cliReadiness.loggedOutTitle' : 'cliReadiness.missingTitle')}
        </strong>{' '}
        <span className="text-muted-foreground">
          {t(installed ? 'cliReadiness.loggedOut' : 'cliReadiness.missing')}
        </span>
      </span>
      <Button size="sm" variant="outline" asChild>
        <Link to="/ajustes">{t('cliReadiness.open')}</Link>
      </Button>
    </div>
  )
}
