import { Globe } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useRemotes, useRepoStatus } from '@/api/git'
import {
  useAddRemote,
  useEditRemote,
  useForcePush,
  useOverwrites,
  useRemoveRemote,
  useTestRemote,
} from '@/api/git-more'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useGitJobs } from '@/stores/git-jobs'
import { gitErrorText } from './git-errors'

/** Remotes (add, change the URL, rename, remove, test) and the forced push, which first shows
 * the commits it would destroy. */
export function RemotesSection({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const remotes = useRemotes(repoId)
  const status = useRepoStatus(repoId)
  const add = useAddRemote(repoId)
  const edit = useEditRemote(repoId)
  const remove = useRemoveRemote(repoId)
  const test = useTestRemote(repoId)
  const force = useForcePush(repoId)
  const upsert = useGitJobs((state) => state.upsert)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [editing, setEditing] = useState<{ name: string; url: string; rename: string } | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)
  const [forcing, setForcing] = useState(false)
  const [checks, setChecks] = useState<Record<string, string>>({})
  const overwrites = useOverwrites(repoId, forcing)
  const branch = status.data?.branch ?? null

  async function run(action: Promise<unknown>, done?: string) {
    try {
      await action
      if (done) toast.success(done)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onAdd(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim() || !url.trim()) return
    await run(add.mutateAsync({ name: name.trim(), url: url.trim() }))
    setName('')
    setUrl('')
  }

  async function onTest(remoteName: string) {
    try {
      const result = await test.mutateAsync(remoteName)
      setChecks((current) => ({
        ...current,
        [remoteName]: result.ok
          ? t('git.remotes.reachable', { count: result.branches })
          : t(`git.errors.${result.error_code ?? 'git_failed'}`, { defaultValue: result.message }),
      }))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onForce() {
    setForcing(false)
    try {
      upsert(await force.mutateAsync({}))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  if (remotes.isPending) return <Skeleton aria-busy className="m-6 h-40 rounded-lg" />

  return (
    <div className="flex flex-col gap-3 px-6 py-4">
      <form onSubmit={(event) => void onAdd(event)} className="flex flex-wrap gap-2">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('git.remotes.name')}
          aria-label={t('git.remotes.name')}
          className="h-8 w-32 font-mono text-xs"
        />
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder={t('git.remotes.url')}
          aria-label={t('git.remotes.url')}
          className="h-8 w-80 font-mono text-xs"
        />
        <Button type="submit" size="sm" disabled={!name.trim() || !url.trim() || add.isPending}>
          <Globe />
          {t('git.remotes.add')}
        </Button>
      </form>

      {(remotes.data ?? []).length === 0 ? (
        <EmptyState icon={Globe} title={t('git.remotes.empty')} />
      ) : (
        <ul className="overflow-hidden rounded-lg border border-sep bg-card">
          {(remotes.data ?? []).map((remote) => (
            <li
              key={remote.name}
              className="flex flex-col gap-1.5 border-b border-sep px-3 py-2 text-[13px] last:border-b-0"
            >
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-mono font-medium">{remote.name}</span>
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
                  {remote.fetch_url}
                </span>
                <span className="flex gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    aria-label={`${t('git.remotes.test')} ${remote.name}`}
                    onClick={() => void onTest(remote.name)}
                  >
                    {t('git.remotes.test')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      setEditing({ name: remote.name, url: remote.fetch_url, rename: remote.name })
                    }
                  >
                    {t('git.remotes.edit')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    aria-label={`${t('git.remotes.remove')} ${remote.name}`}
                    onClick={() => setRemoving(remote.name)}
                  >
                    {t('git.remotes.remove')}
                  </Button>
                </span>
              </div>
              {checks[remote.name] && (
                <p role="status" className="text-xs text-muted-foreground">
                  {checks[remote.name]}
                </p>
              )}
              {editing?.name === remote.name && (
                <form
                  className="flex flex-wrap gap-2"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void run(
                      edit.mutateAsync({
                        name: remote.name,
                        url:
                          editing.url.trim() !== remote.fetch_url ? editing.url.trim() : undefined,
                        rename_to:
                          editing.rename.trim() !== remote.name ? editing.rename.trim() : undefined,
                      }),
                    ).then(() => setEditing(null))
                  }}
                >
                  <Input
                    value={editing.rename}
                    onChange={(e) => setEditing({ ...editing, rename: e.target.value })}
                    aria-label={t('git.remotes.name')}
                    className="h-7 w-32 font-mono text-xs"
                  />
                  <Input
                    value={editing.url}
                    onChange={(e) => setEditing({ ...editing, url: e.target.value })}
                    aria-label={t('git.remotes.url')}
                    className="h-7 w-80 font-mono text-xs"
                  />
                  <Button type="submit" size="sm">
                    {t('common.save')}
                  </Button>
                </form>
              )}
            </li>
          ))}
        </ul>
      )}

      <section className="flex flex-col gap-2 rounded-lg border border-sep p-3">
        <h3 className="text-[13px] font-medium">{t('git.remotes.forceTitle')}</h3>
        <p className="text-xs text-muted-foreground">{t('git.remotes.forceHelp')}</p>
        <div>
          <Button
            type="button"
            size="sm"
            variant="destructive"
            disabled={!branch || force.isPending}
            onClick={() => setForcing(true)}
          >
            {t('git.remotes.force', { branch: branch ?? '' })}
          </Button>
        </div>
      </section>

      <ConfirmDialog
        open={forcing}
        onOpenChange={setForcing}
        title={t('git.remotes.forceConfirmTitle', { branch: branch ?? '' })}
        description={
          overwrites.isPending
            ? t('git.remotes.checking')
            : (overwrites.data ?? []).length === 0
              ? t('git.remotes.overwritesNone')
              : t('git.remotes.overwrites', {
                  count: overwrites.data?.length ?? 0,
                  commits: (overwrites.data ?? []).join(', '),
                })
        }
        confirmLabel={t('git.remotes.forceConfirm')}
        destructive
        onConfirm={() => void onForce()}
      />
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={t('git.remotes.removeTitle', { name: removing ?? '' })}
        description={t('git.remotes.removeDescription')}
        confirmLabel={t('git.remotes.remove')}
        destructive
        onConfirm={() => {
          const target = removing
          setRemoving(null)
          if (target) void run(remove.mutateAsync(target))
        }}
      />
    </div>
  )
}
