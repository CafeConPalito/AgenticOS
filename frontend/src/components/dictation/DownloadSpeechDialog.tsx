import { Download, Loader2 } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { dictationKeys } from '@/api/dictation'
import {
  useDownloadModel,
  useLocalModels,
  useSelectModel,
  type LocalModel,
} from '@/api/local-models'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useKnowledgeEvents } from '@/hooks/use-knowledge-events'
import { ApiError } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'
import { formatBytes } from '@/lib/format'
import { useDictation } from '@/stores/dictation'

const ENGINE_ID = 'whisper-cpp'

function Row({ label, model }: { label: string; model: LocalModel | undefined }) {
  const { t } = useTranslation()
  if (!model) return null
  const percent = model.total > 0 ? Math.round((model.done / model.total) * 100) : 0
  return (
    <li className="flex flex-col gap-1.5 rounded-lg border px-3.5 py-3">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-[11.5px] text-muted-foreground">{label}</div>
          <div className="text-[13.5px] font-medium">{model.title}</div>
        </div>
        <span className="font-mono text-[12px] text-muted-foreground tabular-nums">
          {model.state === 'ready' ? '✓' : formatBytes(model.size)}
        </span>
      </div>
      {model.state === 'downloading' && (
        <div
          role="progressbar"
          aria-label={t('localModels.progress', { title: model.title })}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted"
        >
          <div
            className="absolute inset-y-0 left-0 bg-primary-action"
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
      {model.state === 'error' && (
        <p role="alert" className="text-[12px] text-status-failed">
          {t(`localModels.errors.${model.error_code ?? 'network'}`, {
            defaultValue: model.error_message ?? t('localModels.errors.network'),
          })}
        </p>
      )}
    </li>
  )
}

/** Opens when someone tries to dictate with no speech engine or model downloaded: offers the
 * recommended ones right there, with their progress, and starts using them when they arrive. */
export function DownloadSpeechDialog() {
  const open = useDictation((s) => s.downloadOpen)
  // The models are only asked for while the dialog is open.
  return open ? <DownloadSpeech /> : null
}

function DownloadSpeech() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const open = true
  const setOpen = useDictation((s) => s.setDownloadOpen)
  useKnowledgeEvents()
  const { data } = useLocalModels()
  const download = useDownloadModel()
  const select = useSelectModel()
  const queryClient = useQueryClient()

  const engine = data?.models.find((m) => m.id === ENGINE_ID)
  const speech = data?.models.filter((m) => m.kind === 'speech') ?? []
  const model = speech.find((m) => m.selected) ?? speech.find((m) => m.default) ?? speech[0]
  const needed = [engine, model].filter((m): m is LocalModel => !!m && m.state !== 'ready')
  const downloading = [engine, model].some((m) => m?.state === 'downloading')
  const ready = Boolean(engine && model && needed.length === 0)

  // Everything arrived: use it, and the microphones start working.
  const modelId = model?.id
  const selectModel = select.mutateAsync
  useEffect(() => {
    if (!open || !ready || !modelId) return
    void selectModel({ speech: modelId })
      .then(() => queryClient.invalidateQueries({ queryKey: dictationKeys.status }))
      .then(() => {
        toast.success(t('dictation.download.ready'))
        setOpen(false)
      })
      .catch((error: unknown) => toast.error(errorMessage(error)))
  }, [open, ready, modelId, selectModel, queryClient, setOpen, t])

  async function start() {
    for (const item of needed) {
      if (item.state === 'downloading') continue
      try {
        await download.mutateAsync(item.id)
      } catch (error) {
        toast.error(
          error instanceof ApiError
            ? t(`localModels.errors.${error.code}`, { defaultValue: error.message })
            : errorMessage(error),
        )
      }
    }
  }

  const total = needed.reduce((sum, item) => sum + item.size, 0)
  const resuming = needed.some((m) => m.state === 'partial')

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t('dictation.download.title')}</DialogTitle>
          <DialogDescription>{t('dictation.download.description')}</DialogDescription>
        </DialogHeader>
        <ul className="flex flex-col gap-2">
          <Row label={t('dictation.download.engine')} model={engine} />
          <Row label={t('dictation.download.model')} model={model} />
        </ul>
        {needed.length > 0 && (
          <p className="text-[12px] text-muted-foreground">
            {t('dictation.download.total', { size: formatBytes(total) })}
          </p>
        )}
        <DialogFooter className="gap-2 sm:justify-between">
          <Button
            variant="ghost"
            onClick={() => {
              setOpen(false)
              void navigate('/settings#models')
            }}
          >
            {t('dictation.download.another')}
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t('dictation.download.later')}
            </Button>
            <Button
              disabled={downloading || needed.length === 0 || !data}
              onClick={() => void start()}
            >
              {downloading ? <Loader2 className="animate-spin" /> : <Download />}
              {downloading
                ? t('dictation.download.downloading')
                : resuming
                  ? t('dictation.download.resume')
                  : t('dictation.download.start')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
