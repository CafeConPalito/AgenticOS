import { invoke, isTauri } from '@tauri-apps/api/core'
import { save } from '@tauri-apps/plugin-dialog'
import { FileArchive, FolderOpen, Mail, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { type LogsBundle, revealBundle, useBundleLogs, useLogsPreview } from '@/api/support'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useHealth } from '@/hooks/useHealth'
import { bugReportHref } from '@/lib/bug-report'
import { errorMessage } from '@/lib/form-errors'
import { formatBytes } from '@/lib/format'

const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path
/** Always in the zip (backend/services/support.py). */
const INFO_FILE = 'info.txt'

/** Where to write the zip: «Guardar como» in the desktop app; null when cancelled. */
async function chooseTarget(suggested: string): Promise<string | null | undefined> {
  if (!isTauri()) return undefined // the browser: the backend writes it to Downloads
  return save({ defaultPath: suggested, filters: [{ name: 'Zip', extensions: ['zip'] }] })
}

/**
 * «Preparar registros para enviar» (phase 20, CA12/CA13): what goes in, «Guardar como», and
 * then the folder and the e-mail to attach it to. With `offline` (the backend is down) the
 * desktop shell zips its own log and the backend's.
 */
export function LogsDialog({
  open,
  onOpenChange,
  offline = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  offline?: boolean
}) {
  const { t } = useTranslation()
  const l = 'support.logs'
  const preview = useLogsPreview(open && !offline)
  const bundle = useBundleLogs()
  const [done, setDone] = useState<Pick<LogsBundle, 'path' | 'files' | 'redactions'> | null>(null)
  const [working, setWorking] = useState(false)
  const health = useHealth().data

  function close(next: boolean) {
    if (!next) setDone(null)
    onOpenChange(next)
  }

  async function prepare() {
    setWorking(true)
    try {
      const suggested = preview.data?.default_path ?? 'agentic-os-registros.zip'
      const target = await chooseTarget(suggested)
      if (target === null) return
      if (offline) {
        if (!target) return
        const files = await invoke<string[]>('bundle_logs', { path: target })
        setDone({ path: target, files, redactions: {} })
      } else {
        const made = await bundle.mutateAsync(target ?? null)
        setDone(made)
        // The desktop shell shows it right away; the browser waits for «Mostrar».
        if (isTauri()) void revealBundle(made.path).catch(() => {})
      }
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setWorking(false)
    }
  }

  const mailto = done
    ? bugReportHref({
        version: __APP_VERSION__,
        backendVersion: health?.version,
        attachment: { name: fileName(done.path), note: t(`${l}.attach`) },
        texts: {
          subject: t('about.bug.subject'),
          doing: t('about.bug.doing'),
          expected: t('about.bug.expected'),
          happened: t('about.bug.happened'),
          logs: t('about.bug.logs'),
        },
      })
    : ''
  const hidden = done ? Object.values(done.redactions).reduce((a, b) => a + b, 0) : 0

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{t(`${l}.title`)}</DialogTitle>
          <DialogDescription>{t(offline ? `${l}.offlineText` : `${l}.text`)}</DialogDescription>
        </DialogHeader>
        {done ? (
          <div className="flex flex-col gap-3 text-[13px]">
            <p className="flex items-center gap-2 font-medium">
              <FileArchive className="size-4" />
              {t(`${l}.saved`, { name: fileName(done.path) })}
            </p>
            <p className="font-mono text-xs break-all text-muted-foreground">{done.path}</p>
            <ul className="list-disc pl-5 text-xs text-muted-foreground">
              {done.files.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
            {!offline && (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <ShieldCheck className="size-3.5" />
                {t(`${l}.hidden`, { count: hidden })}
              </p>
            )}
            <DialogFooter>
              {!offline && (
                <Button variant="outline" onClick={() => void revealBundle(done.path)}>
                  <FolderOpen />
                  {t(`${l}.reveal`)}
                </Button>
              )}
              <Button
                asChild
                className="bg-primary-action text-white hover:bg-primary-action-hover"
              >
                <a href={mailto}>
                  <Mail />
                  {t(`${l}.mail`)}
                </a>
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="flex flex-col gap-3 text-[13px]">
            {!offline && (
              <div className="rounded-lg border border-sep">
                {preview.data?.files.length ? (
                  <ul className="divide-y divide-sep">
                    {preview.data.files.map((file) => (
                      <li
                        key={file.name}
                        className="flex justify-between px-3 py-1.5 font-mono text-xs"
                      >
                        <span>{file.name}</span>
                        <span className="text-muted-foreground">{formatBytes(file.size)}</span>
                      </li>
                    ))}
                    <li className="flex justify-between px-3 py-1.5 font-mono text-xs">
                      <span>{INFO_FILE}</span>
                      <span className="text-muted-foreground">{t(`${l}.infoFile`)}</span>
                    </li>
                  </ul>
                ) : (
                  <p className="px-3 py-2 text-xs text-muted-foreground">
                    {preview.isPending ? t(`${l}.loading`) : t(`${l}.noLogs`)}
                  </p>
                )}
              </div>
            )}
            <p className="text-xs text-muted-foreground">{t(`${l}.privacy`)}</p>
            <DialogFooter>
              <Button
                disabled={working || (!offline && preview.isPending)}
                onClick={() => void prepare()}
                className="bg-primary-action text-white hover:bg-primary-action-hover"
              >
                <FileArchive />
                {working ? t(`${l}.working`) : t(isTauri() ? `${l}.saveAs` : `${l}.saveDownloads`)}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
