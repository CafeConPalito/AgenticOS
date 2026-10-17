import { Tag } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { type TagInfo, useCreateTag, useDeleteTag, useTagOnRemote, useTags } from '@/api/git-more'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { relativeTime } from '@/lib/time'
import { useGitJobs } from '@/stores/git-jobs'
import { gitErrorText } from './git-errors'

/** Tags: lightweight or annotated, on any commit, published on the remote or removed from it. */
export function TagsSection({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const tags = useTags(repoId)
  const create = useCreateTag(repoId)
  const remove = useDeleteTag(repoId)
  const onRemote = useTagOnRemote(repoId)
  const upsert = useGitJobs((state) => state.upsert)
  const [name, setName] = useState('')
  const [ref, setRef] = useState('')
  const [message, setMessage] = useState('')
  const [deleting, setDeleting] = useState<TagInfo | null>(null)

  async function run(action: Promise<unknown>, done?: string) {
    try {
      await action
      if (done) toast.success(done)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function publish(tag: TagInfo, drop: boolean) {
    try {
      upsert(await onRemote.mutateAsync({ name: tag.name, delete: drop }))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onCreate(event: React.FormEvent) {
    event.preventDefault()
    const value = name.trim()
    if (!value) return
    await run(
      create.mutateAsync({
        name: value,
        ref: ref.trim() || undefined,
        message: message.trim() || undefined,
      }),
      t('git.tags.created', { name: value }),
    )
    setName('')
    setRef('')
    setMessage('')
  }

  if (tags.isPending) return <Skeleton aria-busy className="m-6 h-40 rounded-lg" />

  return (
    <div className="flex flex-col gap-3 px-6 py-4">
      <form onSubmit={(event) => void onCreate(event)} className="flex flex-wrap gap-2">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('git.tags.name')}
          aria-label={t('git.tags.name')}
          className="h-8 w-40 font-mono text-xs"
        />
        <Input
          value={ref}
          onChange={(e) => setRef(e.target.value)}
          placeholder={t('git.tags.ref')}
          aria-label={t('git.tags.ref')}
          className="h-8 w-40 font-mono text-xs"
        />
        <Input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={t('git.tags.message')}
          aria-label={t('git.tags.message')}
          className="h-8 w-64 text-xs"
        />
        <Button type="submit" size="sm" disabled={!name.trim() || create.isPending}>
          <Tag />
          {t('git.tags.create')}
        </Button>
      </form>

      {(tags.data ?? []).length === 0 ? (
        <EmptyState icon={Tag} title={t('git.tags.empty')} />
      ) : (
        <ul className="overflow-hidden rounded-lg border border-sep bg-card">
          {(tags.data ?? []).map((tag) => (
            <li
              key={tag.name}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-sep px-3 py-2 text-[13px] last:border-b-0"
            >
              <span className="font-mono">{tag.name}</span>
              {tag.annotated && <Badge variant="secondary">{t('git.tags.annotated')}</Badge>}
              <span className="font-mono text-xs text-muted-foreground">{tag.sha.slice(0, 7)}</span>
              <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                {tag.message}
              </span>
              {tag.date && (
                <span className="text-xs text-muted-foreground">{relativeTime(tag.date)}</span>
              )}
              <span className="flex gap-1">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  aria-label={`${t('git.tags.publish')} ${tag.name}`}
                  onClick={() => void publish(tag, false)}
                >
                  {t('git.tags.publish')}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  aria-label={`${t('git.tags.delete')} ${tag.name}`}
                  onClick={() => setDeleting(tag)}
                >
                  {t('git.tags.delete')}
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t('git.tags.deleteTitle', { name: deleting?.name ?? '' })}
        description={t('git.tags.deleteDescription')}
        confirmLabel={t('git.tags.delete')}
        destructive
        onConfirm={() => {
          const tag = deleting
          setDeleting(null)
          if (tag) void run(remove.mutateAsync(tag.name), t('git.tags.deleted', { name: tag.name }))
        }}
      />
    </div>
  )
}
