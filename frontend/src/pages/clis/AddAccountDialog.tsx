import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useCreateAccount } from '@/api/accounts'
import type { CliId } from '@/api/types'
import { Field } from '@/components/page'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/form-errors'

/**
 * «Añadir cuenta»: a name (optional) and the email to pre-fill on the login page. The account
 * is created with a login folder of its own and its login terminal opens right away.
 */
export function AddAccountDialog({
  cli,
  onClose,
  onLogin,
}: {
  cli: CliId | null
  onClose: () => void
  onLogin: (accountId: string, email: string) => void
}) {
  return (
    <Dialog open={cli !== null} onOpenChange={(open) => !open && onClose()}>
      {cli && <AddBody cli={cli} onClose={onClose} onLogin={onLogin} />}
    </Dialog>
  )
}

function AddBody({
  cli,
  onClose,
  onLogin,
}: {
  cli: CliId
  onClose: () => void
  onLogin: (accountId: string, email: string) => void
}) {
  const { t } = useTranslation()
  const create = useCreateAccount()
  const [label, setLabel] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const busy = create.isPending

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const account = await create.mutateAsync({ cli, label: label.trim() })
      onClose()
      onLogin(account.id, email.trim())
    } catch (failure) {
      setError(errorMessage(failure))
    }
  }

  return (
    <DialogContent className="sm:max-w-[460px]">
      <form onSubmit={(e) => void submit(e)} className="grid gap-4">
        <DialogHeader>
          <DialogTitle>{t('accounts.add.title', { cli: t(`cli.${cli}`) })}</DialogTitle>
          <DialogDescription>{t('accounts.add.description')}</DialogDescription>
        </DialogHeader>
        <Field
          label={t('accounts.add.label')}
          htmlFor="account-label"
          help={t('accounts.add.labelHelp')}
        >
          <Input
            id="account-label"
            value={label}
            maxLength={120}
            onChange={(e) => setLabel(e.target.value)}
            placeholder={t('accounts.add.labelPlaceholder')}
          />
        </Field>
        <Field
          label={t('accounts.add.email')}
          htmlFor="account-email"
          help={t('accounts.add.emailHelp')}
        >
          <Input
            id="account-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="nombre@correo.es"
          />
        </Field>
        {error && (
          <p role="alert" className="text-sm text-status-failed">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            disabled={busy}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('accounts.add.submit')}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}
