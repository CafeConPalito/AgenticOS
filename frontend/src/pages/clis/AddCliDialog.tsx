import { CheckCircle2, ExternalLink, XCircle } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useInstallCli, useRefreshClis } from '@/api/clis'
import type { CliId, CliInfo } from '@/api/types'
import { CliIcon } from '@/components/agentic/CliIcon'
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
import { cn } from '@/lib/utils'
import { useLoginTerminal } from './use-login-terminal'

/**
 * «Añadir CLI» (phase 23, ADR 0029): a CLI the app supports and is not installed, installed
 * with its official installer. The command is shown before it runs; it runs in a terminal the
 * person sees; when it ends the CLIs are probed again and the login comes next.
 */
export function AddCliDialog({
  open,
  missing,
  onClose,
  onLogin,
}: {
  open: boolean
  /** The supported CLIs not installed. */
  missing: CliInfo[]
  onClose: () => void
  /** Installed: the next step, its login. */
  onLogin: (cli: CliId) => void
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      {open && <AddCliBody missing={missing} onClose={onClose} onLogin={onLogin} />}
    </Dialog>
  )
}

type Step = { phase: 'choose' } | { phase: 'installing' } | { phase: 'done'; code: number | null }

function AddCliBody({
  missing,
  onClose,
  onLogin,
}: {
  missing: CliInfo[]
  onClose: () => void
  onLogin: (cli: CliId) => void
}) {
  const { t } = useTranslation()
  const a = 'clis.addCli'
  const install = useInstallCli()
  const refresh = useRefreshClis()
  const [chosen, setChosen] = useState<CliInfo | undefined>(missing[0])
  const [step, setStep] = useState<Step>({ phase: 'choose' })

  async function start() {
    if (!chosen) return
    try {
      await install.mutateAsync(chosen.id)
      setStep({ phase: 'installing' })
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function ended(code: number | null) {
    const clis = await refresh().catch(() => undefined)
    const found = clis?.find((c) => c.id === chosen?.id)?.installed ?? false
    setStep({ phase: 'done', code: code === 0 && !found ? -1 : code })
  }

  return (
    <DialogContent className="sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>{t(`${a}.title`)}</DialogTitle>
        <DialogDescription>{t(`${a}.description`)}</DialogDescription>
      </DialogHeader>

      {step.phase === 'choose' && (
        <>
          <div role="radiogroup" aria-label={t(`${a}.choose`)} className="flex flex-col gap-2">
            {missing.map((cli) => (
              <button
                key={cli.id}
                type="button"
                role="radio"
                aria-checked={chosen?.id === cli.id}
                onClick={() => setChosen(cli)}
                className={cn(
                  'flex items-center gap-3 rounded-xl border border-sep p-3 text-left hover:bg-accent',
                  chosen?.id === cli.id && 'ring-2 ring-ring',
                )}
              >
                <CliIcon cli={cli.id} label={cli.name} size={28} />
                <span className="text-[14px] font-medium">{cli.name}</span>
              </button>
            ))}
          </div>
          {chosen &&
            (chosen.installer ? (
              <div className="flex flex-col gap-1.5">
                <p className="text-[13px]">{t(`${a}.willRun`)}</p>
                <pre className="overflow-x-auto rounded-lg border border-sep bg-subtle px-3 py-2 font-mono text-[12.5px]">
                  {chosen.installer.command}
                </pre>
                <p className="text-xs text-muted-foreground">
                  {t(`${a}.official`)}{' '}
                  <DocsLink href={chosen.installer.docs_url}>{t(`${a}.docs`)}</DocsLink>
                </p>
              </div>
            ) : (
              <p className="text-[13px] text-muted-foreground">{t(`${a}.noInstaller`)}</p>
            ))}
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => void start()}
              disabled={!chosen?.installer || install.isPending}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              {t(`${a}.install`)}
            </Button>
          </DialogFooter>
        </>
      )}

      {step.phase !== 'choose' && chosen && (
        <>
          <InstallTerminal cli={chosen.id} onExit={(code) => void ended(code)} />
          {step.phase === 'done' &&
            (step.code === 0 ? (
              <p role="status" className="flex items-center gap-2 text-[13px] text-status-done">
                <CheckCircle2 className="size-4" />
                {t(`${a}.installed`, { name: chosen.name })}
              </p>
            ) : (
              <p role="alert" className="flex flex-wrap items-center gap-2 text-[13px]">
                <XCircle className="size-4 text-status-failed" />
                {step.code === -1
                  ? t(`${a}.notFound`, { name: chosen.name })
                  : t(`${a}.failed`, { code: step.code ?? '?' })}
                {chosen.installer && (
                  <DocsLink href={chosen.installer.docs_url}>{t(`${a}.docs`)}</DocsLink>
                )}
              </p>
            ))}
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t('common.close')}
            </Button>
            {step.phase === 'done' && step.code === 0 && (
              <Button
                onClick={() => onLogin(chosen.id)}
                className="bg-primary-action text-white hover:bg-primary-action-hover"
              >
                {t(`${a}.login`)}
              </Button>
            )}
          </DialogFooter>
        </>
      )}
    </DialogContent>
  )
}

function InstallTerminal({ cli, onExit }: { cli: CliId; onExit: (code: number | null) => void }) {
  const { t } = useTranslation()
  const { containerRef } = useLoginTerminal(cli, onExit, `/api/clis/${cli}/install/terminal`)
  return (
    <div
      ref={containerRef}
      aria-label={t('clis.addCli.terminal')}
      className="h-[300px] overflow-hidden rounded-lg border bg-terminal p-2"
    />
  )
}

function DocsLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 underline"
    >
      {children}
      <ExternalLink className="size-3" />
    </a>
  )
}
