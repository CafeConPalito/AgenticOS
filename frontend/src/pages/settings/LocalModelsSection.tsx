import { Download, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useCancelModel,
  useDeleteModel,
  useDownloadModel,
  useHfToken,
  useLocalModels,
  useSaveHfToken,
  useSelectModel,
  type LocalModel,
  type ModelKind,
} from '@/api/local-models'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useKnowledgeEvents } from '@/hooks/use-knowledge-events'
import { ApiError } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'
import { formatBytes } from '@/lib/format'

const KINDS: ModelKind[] = ['embedding', 'ocr', 'vision', 'speech', 'engine']
const JOB: Partial<Record<ModelKind, 'embedding' | 'ocr' | 'vision' | 'speech'>> = {
  embedding: 'embedding',
  ocr: 'ocr',
  vision: 'vision',
  speech: 'speech',
}

function Row({ model }: { model: LocalModel }) {
  const { t } = useTranslation()
  const download = useDownloadModel()
  const cancel = useCancelModel()
  const remove = useDeleteModel()
  const select = useSelectModel()
  const [removing, setRemoving] = useState(false)
  const job = JOB[model.kind]
  const percent = model.total > 0 ? Math.round((model.done / model.total) * 100) : 0
  // Chosen is not in use until it is on disk (phase 21): until then it is only advised.
  const inUse = model.selected && model.state === 'ready'

  async function run(action: () => Promise<unknown>) {
    try {
      await action()
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? t(`localModels.errors.${error.code}`, { defaultValue: error.message })
          : errorMessage(error),
      )
    }
  }

  async function choose() {
    if (!job) return
    try {
      const result = await select.mutateAsync({ [job]: model.id })
      if (result.reindex) toast.info(t('localModels.reindexing'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <li className="flex flex-col gap-1.5 rounded-lg border px-3.5 py-3">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13.5px] font-medium">{model.title}</span>
            {inUse && <Badge>{t('localModels.inUse')}</Badge>}
            {!inUse && (model.default || model.selected) && (
              <Badge variant="outline">{t('localModels.default')}</Badge>
            )}
            {model.bundled && <Badge variant="secondary">{t('localModels.bundled')}</Badge>}
            {model.needs_account && model.state !== 'ready' && (
              <Badge variant="outline">{t('localModels.needsAccount')}</Badge>
            )}
          </div>
          <div className="text-[12px] text-muted-foreground">
            {model.license} · {formatBytes(model.size)}
            {model.speed && model.quality && (
              <>
                {' · '}
                {t('localModels.speechNote', {
                  speed: t(`localModels.speed.${model.speed}`),
                  quality: t(`localModels.quality.${model.quality}`),
                })}
              </>
            )}
            {!model.available && ` · ${t('localModels.unavailable')}`}
          </div>
        </div>
        {model.state === 'ready' && job && !model.selected && (
          <Button
            variant="outline"
            size="sm"
            aria-label={t('localModels.use', { title: model.title })}
            disabled={select.isPending}
            onClick={() => void choose()}
          >
            {t('localModels.useShort')}
          </Button>
        )}
        {model.state === 'downloading' ? (
          <Button
            variant="outline"
            size="sm"
            aria-label={t('localModels.cancel', { title: model.title })}
            onClick={() => void run(() => cancel.mutateAsync(model.id))}
          >
            <X />
            {t('common.cancel')}
          </Button>
        ) : model.state === 'ready' ? (
          !model.bundled && (
            <Button
              variant="outline"
              size="sm"
              aria-label={t('localModels.remove', { title: model.title })}
              onClick={() => setRemoving(true)}
            >
              <Trash2 />
              {t('localModels.removeShort')}
            </Button>
          )
        ) : (
          <Button
            variant="outline"
            size="sm"
            aria-label={t('localModels.download', { title: model.title })}
            disabled={!model.available || download.isPending}
            onClick={() => void run(() => download.mutateAsync(model.id))}
          >
            <Download />
            {model.state === 'partial'
              ? t('localModels.resume')
              : model.state === 'error'
                ? t('localModels.retry')
                : t('localModels.downloadShort')}
          </Button>
        )}
      </div>
      {model.state === 'downloading' && (
        <div className="flex items-center gap-2">
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
          <span className="font-mono text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">
            {formatBytes(model.done)} / {formatBytes(model.total)}
          </span>
        </div>
      )}
      {model.state === 'partial' && (
        <p className="text-[12px] text-muted-foreground">
          {t('localModels.partial', { done: formatBytes(model.done) })}
        </p>
      )}
      {model.state === 'error' && (
        <p role="alert" className="text-[12px] text-status-failed">
          {t(`localModels.errors.${model.error_code ?? 'network'}`, {
            defaultValue: model.error_message ?? t('localModels.errors.network'),
          })}
        </p>
      )}
      <ConfirmDialog
        open={removing}
        onOpenChange={setRemoving}
        title={t('localModels.removeTitle', { title: model.title })}
        description={t('localModels.removeBody')}
        confirmLabel={t('localModels.removeShort')}
        destructive
        onConfirm={() => void run(() => remove.mutateAsync(model.id))}
      />
    </li>
  )
}

function TokenField() {
  const { t } = useTranslation()
  const token = useHfToken()
  const save = useSaveHfToken()
  const [value, setValue] = useState('')

  async function submit(next: string | null) {
    try {
      await save.mutateAsync(next)
      setValue('')
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border bg-subtle p-3">
      <h3 className="text-[13px] font-medium">{t('localModels.token.title')}</h3>
      <p className="text-xs text-muted-foreground">{t('localModels.token.help')}</p>
      {token.data?.configured && (
        <p className="text-[12.5px]">
          {t('localModels.token.configured', {
            source: t(`localModels.token.source.${token.data.source ?? 'git'}`),
          })}
        </p>
      )}
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (value.trim()) void submit(value.trim())
        }}
      >
        <Input
          type="password"
          autoComplete="off"
          aria-label={t('localModels.token.label')}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="hf_…"
          className="font-mono text-[12.5px]"
        />
        <Button type="submit" variant="outline" disabled={!value.trim() || save.isPending}>
          {t('localModels.token.save')}
        </Button>
        {token.data?.configured && token.data.source === 'git' && (
          <Button type="button" variant="ghost" onClick={() => void submit(null)}>
            {t('localModels.token.remove')}
          </Button>
        )}
      </form>
    </div>
  )
}

/** «Modelos locales»: what is downloaded for the library, which one does each job. */
export function LocalModelsSection() {
  const { t } = useTranslation()
  useKnowledgeEvents()
  const { data } = useLocalModels()
  const needsAccount = data?.models.some((m) => m.needs_account && m.state !== 'ready')
  return (
    <section
      aria-labelledby="models-title"
      className="flex flex-col gap-4 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <div>
        <h2 id="models-title" className="text-[15px] font-medium">
          {t('localModels.title')}
        </h2>
        <p className="mt-1 text-[12.5px] text-muted-foreground">{t('localModels.description')}</p>
      </div>
      {!data ? (
        <Skeleton aria-busy className="h-32 rounded-lg" />
      ) : (
        <>
          {KINDS.map((kind) => {
            const models = data.models.filter((m) => m.kind === kind)
            if (models.length === 0) return null
            return (
              <div key={kind} className="flex flex-col gap-2">
                <h3 className="text-[13px] font-medium">{t(`localModels.kinds.${kind}.title`)}</h3>
                <p className="text-xs text-muted-foreground">
                  {t(`localModels.kinds.${kind}.help`)}
                </p>
                <ul className="flex flex-col gap-2">
                  {models.map((model) => (
                    <Row key={model.id} model={model} />
                  ))}
                </ul>
              </div>
            )
          })}
          {needsAccount && <TokenField />}
          <p className="text-xs text-muted-foreground">
            {t('localModels.disk', {
              models: formatBytes(data.disk.models),
              engines: formatBytes(data.disk.engines),
              free: formatBytes(data.disk.free),
            })}
          </p>
        </>
      )}
    </section>
  )
}
