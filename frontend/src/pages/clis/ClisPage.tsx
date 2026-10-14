import { Plus, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { useAccounts, useProbeAccount } from '@/api/accounts'
import { useClis, useRefreshClis } from '@/api/clis'
import type { Account, CliId, CliInfo } from '@/api/types'
import { CliTag } from '@/components/agentic/primitives'
import { PageContainer, PageHeader } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import { AccountCard } from './AccountCard'
import { AccountLoginDialog } from './AccountLoginDialog'
import { AddAccountDialog } from './AddAccountDialog'

/** Only Claude Code can have several logins: agy keeps its single one in the system's store. */
const MULTI_ACCOUNT: CliId[] = ['claude']

/**
 * «CLIs y cuentas»: each CLI with its logins. A login is an account: it has its own session,
 * daily limit and subscription windows, and each agent can use the one it needs.
 */
export default function ClisPage() {
  const { t } = useTranslation()
  const clis = useClis().data
  const refreshClis = useRefreshClis()
  const accounts = useAccounts().data
  const probe = useProbeAccount()
  const [params, setParams] = useSearchParams()
  const [login, setLogin] = useState<{ id: string; email: string } | null>(null)
  const [adding, setAdding] = useState<CliId | null>(null)
  const [checking, setChecking] = useState(false)

  // `?reconectar=<account>` (a logged-out notice) opens that account's login and `?nueva=1`
  // (Ctrl+K, the summary's «+») opens «Añadir cuenta»: the page follows the URL.
  const reconnect = params.get('reconectar')
  const loginId =
    login?.id ?? (reconnect && accounts?.some((a) => a.id === reconnect) ? reconnect : null)
  const addingCli: CliId | null = adding ?? (params.get('nueva') ? 'claude' : null)

  function clearLinks() {
    if (params.has('reconectar') || params.has('nueva')) setParams({}, { replace: true })
  }

  async function check() {
    setChecking(true)
    try {
      await refreshClis()
      for (const account of accounts ?? []) await probe.mutateAsync(account.id).catch(() => null)
      toast.success(t('clis.checked'))
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setChecking(false)
    }
  }

  return (
    <PageContainer narrow>
      <PageHeader
        title={t('clis.title')}
        subtitle={t('clis.subtitle')}
        actions={
          <>
            <Button variant="outline" disabled={checking} onClick={() => void check()}>
              <RefreshCw className={cn(checking && 'animate-spin')} />
              {t('clis.check')}
            </Button>
            <Button
              onClick={() => setAdding('claude')}
              className="rounded-full bg-primary-action text-white hover:bg-primary-action-hover"
            >
              <Plus />
              {t('clis.addAccount')}
            </Button>
          </>
        }
      />
      {!clis || !accounts ? (
        <Skeleton className="h-64 rounded-2xl" />
      ) : (
        clis.map((cli) => (
          <CliSection
            key={cli.id}
            cli={cli}
            accounts={accounts.filter((a) => a.cli === cli.id)}
            onLogin={(account) => setLogin({ id: account.id, email: account.email })}
            onAdd={() => setAdding(cli.id)}
          />
        ))
      )}
      <AddAccountDialog
        cli={addingCli}
        onClose={() => {
          setAdding(null)
          clearLinks()
        }}
        onLogin={(id, email) => setLogin({ id, email })}
      />
      <AccountLoginDialog
        accountId={loginId}
        email={login?.email}
        onClose={() => {
          setLogin(null)
          clearLinks()
        }}
      />
    </PageContainer>
  )
}

function CliSection({
  cli,
  accounts,
  onLogin,
  onAdd,
}: {
  cli: CliInfo
  accounts: Account[]
  onLogin: (account: Account) => void
  onAdd: () => void
}) {
  const { t } = useTranslation()
  const live = accounts.reduce((sum, a) => sum + a.live_runs, 0)
  const canAdd = cli.installed && MULTI_ACCOUNT.includes(cli.id)
  return (
    <section
      aria-label={cli.name}
      className="overflow-hidden rounded-2xl border border-sep shadow-card bg-card-grad"
    >
      <header className="flex flex-wrap items-center gap-3 border-b border-sep px-4 py-3.5">
        <CliTag cli={cli.id} label={t(`cli.${cli.id}`)} size={32} />
        <div className="min-w-0 flex-1">
          <h2 className="text-[14px] font-medium">{cli.name}</h2>
          <p className="text-xs text-muted-foreground">
            {t(`cli.vendor.${cli.id}`)} ·{' '}
            <span className="font-mono">
              {cli.version ? `v${cli.version.split(' ')[0]}` : t('clis.noVersion')}
            </span>{' '}
            · {t('accounts.sessions', { count: live })}
          </p>
        </div>
        <span className={cn('text-xs', cli.installed ? 'text-status-done' : 'text-status-failed')}>
          {cli.installed ? t('clis.installed') : t('clis.notDetected')}
        </span>
        {canAdd && (
          <Button size="sm" variant="outline" onClick={onAdd}>
            <Plus />
            {t('accounts.add.button')}
          </Button>
        )}
      </header>
      {!cli.installed ? (
        <p className="px-4 py-3.5 text-[13px] text-muted-foreground">
          {t(`clis.install.${cli.id}`)}
        </p>
      ) : (
        <>
          <ul aria-label={t('clis.accountsOf', { cli: cli.name })}>
            {accounts.map((account) => (
              <AccountCard key={account.id} account={account} onLogin={onLogin} />
            ))}
          </ul>
          {cli.id === 'agy' && (
            <p className="border-t border-sep px-4 py-2.5 text-xs text-muted-foreground">
              {t('clis.single.agy')}
            </p>
          )}
        </>
      )}
    </section>
  )
}
