import { isTauri } from '@tauri-apps/api/core'
import { ExternalLink, FolderSearch, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useDeleteDoc,
  useDocImages,
  useKnowledgeDoc,
  useOpenDoc,
  useReprocessDoc,
  useRelocateDoc,
  useRevealDoc,
  useUpdateDoc,
  type DocPatch,
  type KnowledgeDoc,
  type KnowledgeMode,
} from '@/api/knowledge'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { ApiError } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'
import { formatBytes } from '@/lib/format'
import { pickFiles } from '@/lib/native-files'
import { isPending } from './status'
import { DocViewer } from './DocViewer'
import { ProposalReview, SourcesList } from './ProposalReview'
import { relativeTime } from '@/lib/time'

const MODES: KnowledgeMode[] = ['auto', 'context', 'search', 'off']
type DescribeChoice = 'default' | 'yes' | 'no'

const choiceOf = (value: boolean | null): DescribeChoice =>
  value === null ? 'default' : value ? 'yes' : 'no'
const valueOf = (choice: DescribeChoice): boolean | null =>
  choice === 'default' ? null : choice === 'yes'

function Images({ doc }: { doc: KnowledgeDoc }) {
  const { t } = useTranslation()
  const images = useDocImages(doc.id, doc.image_count > 0)
  if (doc.image_count === 0 || !images.data?.length) return null
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-[13px] font-medium">
        {t('knowledge.sheet.images', { count: images.data.length })}
      </h3>
      <ul className="flex flex-col gap-1.5">
        {images.data.map((image) => (
          <li key={image.ord} className="rounded border px-2.5 py-1.5 text-[12.5px]">
            <div className="text-muted-foreground">
              {image.location || t('knowledge.sheet.imageN', { n: image.ord + 1 })}
              {image.described_by &&
                ` · ${t('knowledge.sheet.describedBy', { by: image.described_by })}`}
            </div>
            {image.description && <p>{image.description}</p>}
            {image.ocr_text && (
              <p className="text-muted-foreground">
                {t('knowledge.sheet.ocr')}: {image.ocr_text}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Relocate({ doc }: { doc: KnowledgeDoc }) {
  const { t } = useTranslation()
  const relocate = useRelocateDoc()
  const [path, setPath] = useState('')
  const [asking, setAsking] = useState(false)

  async function run(confirm: boolean) {
    try {
      const result = await relocate.mutateAsync({ id: doc.id, path: path.trim(), confirm })
      toast.success(
        result.reprocess ? t('knowledge.sheet.relocatedAgain') : t('knowledge.sheet.relocated'),
      )
      setPath('')
      setAsking(false)
    } catch (error) {
      if (error instanceof ApiError && error.code === 'different_content') setAsking(true)
      else
        toast.error(
          error instanceof ApiError
            ? t(`knowledge.errors.${error.code}`, { defaultValue: error.message })
            : errorMessage(error),
        )
    }
  }

  async function browse() {
    const [picked] = await pickFiles(t('knowledge.sheet.relocateDialog'), false)
    if (picked) setPath(picked)
  }

  return (
    <section className="flex flex-col gap-2 rounded-lg border border-status-failed/40 p-3">
      <p className="text-[13px]">
        {doc.presence === 'missing'
          ? t('knowledge.sheet.missingHelp')
          : t('knowledge.sheet.changedHelp')}
      </p>
      <div className="flex gap-2">
        <Input
          aria-label={t('knowledge.sheet.newPath')}
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder={t('knowledge.sheet.newPathPlaceholder')}
          className="font-mono text-[12.5px]"
        />
        {isTauri() && (
          <Button type="button" variant="outline" onClick={() => void browse()}>
            {t('knowledge.add.browse')}
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          disabled={!path.trim() || relocate.isPending}
          onClick={() => void run(false)}
        >
          {t('knowledge.sheet.relocate')}
        </Button>
      </div>
      <ConfirmDialog
        open={asking}
        onOpenChange={setAsking}
        title={t('knowledge.sheet.differentTitle')}
        description={t('knowledge.sheet.differentBody')}
        confirmLabel={t('knowledge.sheet.differentConfirm')}
        onConfirm={() => void run(true)}
      />
    </section>
  )
}

/** Who proposed an agent's document, when, from which task, and what it was built on. */
function Provenance({ doc, onOpen }: { doc: KnowledgeDoc; onOpen?: (id: string) => void }) {
  const { t } = useTranslation()
  const provenance = doc.provenance
  if (!provenance && doc.sources.length === 0) return null
  return (
    <section className="flex flex-col gap-2 rounded-lg border p-3">
      <h3 className="text-[13px] font-medium">{t('knowledge.provenance.title')}</h3>
      {provenance && (
        <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1 text-[12.5px]">
          <dt className="text-muted-foreground">{t('knowledge.provenance.agent')}</dt>
          <dd>{provenance.agent_name || t('knowledge.provenance.unknownAgent')}</dd>
          {provenance.task_title && (
            <>
              <dt className="text-muted-foreground">{t('knowledge.provenance.task')}</dt>
              <dd>{provenance.task_title}</dd>
            </>
          )}
          <dt className="text-muted-foreground">{t('knowledge.provenance.proposed')}</dt>
          <dd>{relativeTime(provenance.proposed_at)}</dd>
          {provenance.decided_at && (
            <>
              <dt className="text-muted-foreground">{t('knowledge.provenance.decided')}</dt>
              <dd>
                {relativeTime(provenance.decided_at)}
                {provenance.edited && ` · ${t('knowledge.provenance.edited')}`}
              </dd>
            </>
          )}
        </dl>
      )}
      {doc.sources.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-[12.5px] text-muted-foreground">
            {t('knowledge.provenance.derivedFrom')}
          </span>
          <SourcesList doc={doc} onOpen={onOpen} />
        </div>
      )}
    </section>
  )
}

function Details({
  doc,
  onClose,
  onNavigate,
}: {
  doc: KnowledgeDoc
  onClose: () => void
  onNavigate?: (id: string) => void
}) {
  const { t } = useTranslation()
  const update = useUpdateDoc()
  const reprocess = useReprocessDoc()
  const open = useOpenDoc()
  const reveal = useRevealDoc()
  const remove = useDeleteDoc()
  const [title, setTitle] = useState(doc.title)
  const [description, setDescription] = useState(doc.description)
  const [removing, setRemoving] = useState(false)
  const dirty = title.trim() !== doc.title || description !== doc.description

  async function patch(change: DocPatch) {
    try {
      await update.mutateAsync({ id: doc.id, ...change })
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function act(run: () => Promise<unknown>) {
    try {
      await run()
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  if (doc.review === 'proposed')
    return <ProposalReview doc={doc} onDone={onClose} onOpenSource={onNavigate} />
  const isFile = doc.source_kind === 'file' || doc.source_kind === 'image'
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
      <div className="flex flex-wrap gap-2">
        {isFile && doc.presence !== 'missing' && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void act(() => open.mutateAsync(doc.id))}
          >
            <ExternalLink />
            {t('knowledge.sheet.open')}
          </Button>
        )}
        {isFile && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void act(() => reveal.mutateAsync(doc.id))}
          >
            <FolderSearch />
            {t('knowledge.sheet.reveal')}
          </Button>
        )}
        <Button
          variant="outline"
          size="sm"
          disabled={isPending(doc) && doc.status !== 'queued'}
          onClick={() => void act(() => reprocess.mutateAsync(doc.id))}
        >
          <RefreshCw />
          {t('knowledge.sheet.reprocess')}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="text-status-failed"
          onClick={() => setRemoving(true)}
        >
          <Trash2 />
          {t('knowledge.sheet.remove')}
        </Button>
      </div>

      {doc.status === 'failed' && (
        <p
          role="alert"
          className="rounded border border-status-failed/40 p-2.5 text-[13px] text-status-failed"
        >
          {t(`knowledge.errors.${doc.error_code ?? 'unknown'}`, {
            defaultValue: doc.error_message ?? t('knowledge.errors.unknown'),
          })}
        </p>
      )}
      {doc.notice && (
        <p className="rounded border p-2.5 text-[13px] text-muted-foreground">
          {t(`knowledge.notices.${doc.notice}`, { defaultValue: doc.notice })}
        </p>
      )}
      {isFile && doc.presence !== 'ok' && <Relocate doc={doc} />}
      <Provenance doc={doc} onOpen={onNavigate} />

      <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1 text-[12.5px]">
        <dt className="text-muted-foreground">{t('knowledge.sheet.source')}</dt>
        <dd className="font-mono break-all">
          {doc.source_kind === 'markdown' ? t('knowledge.origin.agent') : (doc.path ?? doc.url)}
        </dd>
        {doc.size !== null && (
          <>
            <dt className="text-muted-foreground">{t('knowledge.sheet.size')}</dt>
            <dd>{formatBytes(doc.size)}</dd>
          </>
        )}
        <dt className="text-muted-foreground">{t('knowledge.sheet.tokens')}</dt>
        <dd>{doc.md_tokens}</dd>
      </dl>

      <div className="flex flex-col gap-3">
        <Input
          aria-label={t('knowledge.sheet.titleLabel')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Textarea
          aria-label={t('knowledge.sheet.descriptionLabel')}
          dictation
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t('knowledge.sheet.descriptionPlaceholder')}
          rows={2}
        />
        <div>
          <Button
            size="sm"
            disabled={!dirty || !title.trim() || update.isPending}
            onClick={() => void patch({ title: title.trim(), description })}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('common.save')}
          </Button>
        </div>
        <div className="flex flex-wrap gap-4">
          <label className="flex flex-col gap-1 text-[12px] text-muted-foreground">
            {t('knowledge.sheet.mode')}
            <Select
              value={doc.mode}
              onValueChange={(mode) => void patch({ mode: mode as KnowledgeMode })}
            >
              <SelectTrigger aria-label={t('knowledge.sheet.mode')} className="h-8 w-[260px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODES.map((mode) => (
                  <SelectItem key={mode} value={mode}>
                    {t(`knowledge.modes.${mode}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <label className="flex flex-col gap-1 text-[12px] text-muted-foreground">
            {t('knowledge.sheet.describe')}
            <Select
              value={choiceOf(doc.describe_images)}
              onValueChange={(choice) =>
                void patch({ describe_images: valueOf(choice as DescribeChoice) })
              }
            >
              <SelectTrigger aria-label={t('knowledge.sheet.describe')} className="h-8 w-[260px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(['default', 'yes', 'no'] as const).map((choice) => (
                  <SelectItem key={choice} value={choice}>
                    {t(`knowledge.describeChoice.${choice}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        </div>
      </div>

      <DocViewer key={doc.id + doc.processed_at} doc={doc} />
      <Images doc={doc} />

      <ConfirmDialog
        open={removing}
        onOpenChange={setRemoving}
        title={t('knowledge.sheet.removeTitle', { title: doc.title })}
        description={t('knowledge.sheet.removeBody')}
        confirmLabel={t('knowledge.sheet.remove')}
        destructive
        onConfirm={() =>
          void act(async () => {
            await remove.mutateAsync(doc.id)
            onClose()
          })
        }
      />
    </div>
  )
}

/** The side sheet of a document: what it is, what can be done to it, and its content. */
export function DocSheet({
  docId,
  onClose,
  onNavigate,
}: {
  docId: string | null
  onClose: () => void
  /** Open another document from this one (a source it was derived from). */
  onNavigate?: (id: string) => void
}) {
  const { t } = useTranslation()
  const doc = useKnowledgeDoc(docId)
  return (
    <Sheet open={docId !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-3xl">
        <SheetHeader className="border-b">
          <SheetTitle>{doc.data?.title ?? t('knowledge.sheet.loading')}</SheetTitle>
          <SheetDescription>{t('knowledge.sheet.description')}</SheetDescription>
        </SheetHeader>
        {doc.data && <Details doc={doc.data} onClose={onClose} onNavigate={onNavigate} />}
      </SheetContent>
    </Sheet>
  )
}
