import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useClean,
  useCleanPreview,
  useGc,
  useRepoSize,
  useVerify,
  type Verification,
} from '@/api/git-more'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { useGitJobs } from '@/stores/git-jobs'
import { gitErrorText } from './git-errors'

/** Upkeep: delete the files git does not track (after showing them), compact the repository,
 * check it and see how big it is. */
export function MaintenanceSection({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const [folders, setFolders] = useState(true)
  const [ignored, setIgnored] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [verification, setVerification] = useState<Verification | null>(null)
  const preview = useCleanPreview(repoId, folders, ignored)
  const clean = useClean(repoId)
  const gc = useGc(repoId)
  const verify = useVerify(repoId)
  const size = useRepoSize(repoId)
  const upsert = useGitJobs((state) => state.upsert)
  const items = [...(preview.data?.files ?? []), ...(preview.data?.folders ?? [])]

  async function attempt(action: Promise<unknown>, done?: string) {
    try {
      await action
      if (done) toast.success(done)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <div className="flex flex-col gap-4 px-6 py-4">
      <section
        aria-label={t('git.maintenance.clean')}
        className="flex flex-col gap-2 rounded-lg border border-sep p-3"
      >
        <h3 className="text-[13px] font-medium">{t('git.maintenance.clean')}</h3>
        <p className="text-xs text-muted-foreground">{t('git.maintenance.cleanHelp')}</p>
        <div className="flex gap-4 text-xs">
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={folders}
              onChange={(e) => setFolders(e.target.checked)}
            />
            {t('git.maintenance.folders')}
          </label>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={ignored}
              onChange={(e) => setIgnored(e.target.checked)}
            />
            {t('git.maintenance.ignored')}
          </label>
        </div>
        {items.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('git.maintenance.nothingToClean')}</p>
        ) : (
          <ul aria-label={t('git.maintenance.willDelete')} className="font-mono text-xs">
            {items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        <div>
          <Button
            type="button"
            size="sm"
            variant="destructive"
            disabled={items.length === 0 || clean.isPending}
            onClick={() => setConfirming(true)}
          >
            {t('git.maintenance.cleanNow', { count: items.length })}
          </Button>
        </div>
      </section>

      <section
        aria-label={t('git.maintenance.repo')}
        className="flex flex-col gap-2 rounded-lg border border-sep p-3"
      >
        <h3 className="text-[13px] font-medium">{t('git.maintenance.repo')}</h3>
        {size.data && (
          <p className="text-xs text-muted-foreground">
            {t('git.maintenance.size', {
              loose: size.data.loose,
              packed: size.data.packed,
              garbage: size.data.garbage,
            })}
          </p>
        )}
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={gc.isPending}
            onClick={() =>
              void gc
                .mutateAsync()
                .then(upsert)
                .catch((error: unknown) => toast.error(gitErrorText(error, t)))
            }
          >
            {t('git.maintenance.gc')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={verify.isPending}
            onClick={() =>
              void attempt(verify.mutateAsync().then((result) => setVerification(result)))
            }
          >
            {t('git.maintenance.verify')}
          </Button>
        </div>
        {verification &&
          (verification.ok ? (
            <p role="status" className="text-xs text-status-done">
              {t('git.maintenance.verifyOk')}
            </p>
          ) : (
            <ul role="alert" className="font-mono text-xs text-status-failed">
              {verification.problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          ))}
      </section>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('git.maintenance.cleanTitle', { count: items.length })}
        description={t(
          ignored ? 'git.maintenance.cleanDescriptionIgnored' : 'git.maintenance.cleanDescription',
        )}
        confirmLabel={t('git.maintenance.cleanConfirm')}
        destructive
        onConfirm={() => {
          setConfirming(false)
          void attempt(
            clean.mutateAsync({ paths: items, folders, ignored }),
            t('git.maintenance.cleaned'),
          )
        }}
      />
    </div>
  )
}
