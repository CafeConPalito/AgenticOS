import { CircleCheck, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAccounts, useCancelLogin, useProbeAccount, useStartLogin } from '@/api/accounts'
import type { Account } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { errorMessage } from '@/lib/form-errors'
import { useLoginTerminal } from './use-login-terminal'

/**
 * The CLI's login in a terminal (Claude Code: `claude auth login`; agy: its own screen). It
 * opens the browser by itself; if it cannot, the terminal prints the address and, sometimes,
 * asks for a code to type. When the CLI ends, the app asks it who is logged in.
 */
export function AccountLoginDialog({
  accountId,
  email = '',
  onClose,
}: {
  accountId: string | null
  /** Pre-fills the email on the login page (a new account). */
  email?: string
  onClose: () => void
}) {
  return (
    <Dialog open={accountId !== null} onOpenChange={(open) => !open && onClose()}>
      {accountId && <LoginBody accountId={accountId} email={email} onClose={onClose} />}
    </Dialog>
  )
}

function LoginBody({
  accountId,
  email,
  onClose,
}: {
  accountId: string
  email: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const accounts = useAccounts().data
  const account: Account | undefined = accounts?.find((a) => a.id === accountId)
  const start = useStartLogin()
  const [started, setStarted] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  // Opening the dialog opens the CLI's login (the one already open, if there is one).
  const { mutate } = start
  useEffect(() => {
    mutate(
      { id: accountId, email },
      {
        onSuccess: () => setStarted(true),
        onError: (error) => setFailed(errorMessage(error)),
      },
    )
  }, [mutate, accountId, email])

  return (
    <DialogContent
      className="sm:max-w-[680px]"
      onInteractOutside={(e) => e.preventDefault()}
      onEscapeKeyDown={(e) => e.preventDefault()}
    >
      <DialogHeader>
        <DialogTitle>
          {t('accounts.login.title', { cli: account ? t(`cli.${account.cli}`) : '' })}
        </DialogTitle>
        <DialogDescription>{t('accounts.login.description')}</DialogDescription>
      </DialogHeader>
      {failed ? (
        <>
          <p role="alert" className="text-sm text-status-failed">
            {failed}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t('accounts.login.close')}
            </Button>
          </DialogFooter>
        </>
      ) : started ? (
        <LoginTerminal accountId={accountId} account={account} onClose={onClose} />
      ) : (
        <p role="status" className="text-sm text-muted-foreground">
          {t('accounts.login.opening')}
        </p>
      )}
    </DialogContent>
  )
}

function LoginTerminal({
  accountId,
  account,
  onClose,
}: {
  accountId: string
  account: Account | undefined
  onClose: () => void
}) {
  const { t } = useTranslation()
  const cancel = useCancelLogin()
  const probe = useProbeAccount()
  const { containerRef, exited } = useLoginTerminal(accountId, () => {
    // The CLI ended: ask who is logged in now (the backend also does, this refreshes the page).
    probe.mutate(accountId, { onError: (error) => toast.error(errorMessage(error)) })
  })
  const done = exited && !probe.isPending
  const loggedIn = account?.session_state === 'ok'

  function close() {
    if (!exited) cancel.mutate(accountId)
    onClose()
  }

  return (
    <>
      <div
        ref={containerRef}
        data-testid="login-terminal"
        className="h-[320px] overflow-hidden rounded-[11px] border bg-terminal px-2 py-1.5"
      />
      {exited && (
        <p
          role="status"
          className={
            loggedIn
              ? 'flex items-center gap-2 text-[13px] text-status-done'
              : 'flex items-center gap-2 text-[13px] text-status-waiting'
          }
        >
          {loggedIn ? (
            <>
              <CircleCheck className="size-4" />
              {t('accounts.login.done', { name: account?.name ?? '' })}
            </>
          ) : probe.isPending ? (
            t('accounts.login.checking')
          ) : (
            <>
              <TriangleAlert className="size-4" />
              {t('accounts.login.notLoggedIn')}
            </>
          )}
        </p>
      )}
      <DialogFooter>
        <Button
          variant={done ? 'default' : 'outline'}
          onClick={close}
          className={done ? 'bg-primary-action text-white hover:bg-primary-action-hover' : ''}
        >
          {done ? t('accounts.login.close') : t('accounts.login.cancel')}
        </Button>
      </DialogFooter>
    </>
  )
}
