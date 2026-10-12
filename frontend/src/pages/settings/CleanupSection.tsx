import { GitBranch, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type TaskBranch,
  useCleanLogs,
  useDeleteBranches,
  useMaintenanceSettings,
  useSaveMaintenanceSettings,
  useTaskBranches,
} from '@/api/maintenance'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/form-errors'
import { formatBytes } from '@/lib/format'
import { formatDateTime } from '@/lib/time'
import { cn } from '@/lib/utils'

const RETENTION_DAYS = [30, 60, 90, 180, 365]
const NEVER = 'never'

/** «Limpieza» (phase 08): the runs' terminal logs and the task branches. */
export function CleanupSection() {
  const { t } = useTranslation()
  return (
    <section
      aria-labelledby="cleanup-title"
      className="flex flex-col gap-4 rounded-xl border bg-card p-4"
    >
      <h2 id="cleanup-title" className="flex items-center gap-2 text-[15px] font-medium">
        <Trash2 className="size-4" />
        {t('settings.cleanup.title')}
      </h2>
      <LogRetention />
      <Branches />
    </section>
  )
}

function LogRetention() {
  const { t } = useTranslation()
  const settings = useMaintenanceSettings().data
  const save = useSaveMaintenanceSettings()
  const clean = useCleanLogs()
  const onError = (error: unknown) => toast.error(errorMessage(error))

  if (!settings) return <Skeleton className="h-16 rounded-lg" />
  const value = settings.log_retention_days === null ? NEVER : String(settings.log_retention_days)
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="log-retention">{t('settings.cleanup.logs')}</Label>
      <p className="text-xs text-muted-foreground">{t('settings.cleanup.logsHelp')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] text-muted-foreground">{t('settings.cleanup.retention')}</span>
        <Select
          value={value}
          onValueChange={(next) =>
            save.mutate({ log_retention_days: next === NEVER ? null : Number(next) }, { onError })
          }
        >
          <SelectTrigger id="log-retention" className="w-[140px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RETENTION_DAYS.map((days) => (
              <SelectItem key={days} value={String(days)}>
                {t('settings.cleanup.retentionDays', { count: days })}
              </SelectItem>
            ))}
            <SelectItem value={NEVER}>{t('settings.cleanup.never')}</SelectItem>
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="sm"
          disabled={clean.isPending || settings.log_retention_days === null}
          onClick={() =>
            clean.mutate(undefined, {
              onSuccess: ({ runs, freed_bytes }) =>
                toast.success(
                  runs
                    ? t('settings.cleanup.cleaned', {
                        count: runs,
                        size: formatBytes(freed_bytes),
                      })
                    : t('settings.cleanup.nothingToClean'),
                ),
              onError,
            })
          }
        >
          {t('settings.cleanup.cleanNow')}
        </Button>
      </div>
    </div>
  )
}

function Branches() {
  const { t } = useTranslation()
  const { data: projects } = useTaskBranches()
  const remove = useDeleteBranches()
  const [unmerged, setUnmerged] = useState<{ projectId: string; branch: string } | null>(null)
  const now = new Date()

  function deleteBranches(projectId: string, branches: string[], force = false) {
    remove.mutate(
      { project_id: projectId, branches, force },
      {
        onSuccess: ({ deleted, failed }) => {
          if (deleted.length)
            toast.success(t('settings.cleanup.deleted', { count: deleted.length }))
          for (const [name, error] of Object.entries(failed))
            toast.error(t('settings.cleanup.deleteFailed', { name, error }))
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  function onDelete(projectId: string, branch: TaskBranch) {
    if (branch.merged) deleteBranches(projectId, [branch.name])
    else setUnmerged({ projectId, branch: branch.name })
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-2 text-sm font-medium">
        <GitBranch className="size-4" />
        {t('settings.cleanup.branches')}
      </span>
      <p className="text-xs text-muted-foreground">{t('settings.cleanup.branchesHelp')}</p>
      {!projects ? (
        <Skeleton className="h-16 rounded-lg" />
      ) : projects.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">{t('settings.cleanup.noBranches')}</p>
      ) : (
        projects.map((project) => {
          const merged = project.branches.filter((b) => b.merged && !b.in_use)
          return (
            <div key={project.project_id} className="rounded-lg border">
              <div className="flex items-center gap-3 border-b px-3 py-2">
                <span className="flex-1 text-[13.5px] font-medium">{project.project_name}</span>
                {merged.length > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={remove.isPending}
                    onClick={() =>
                      deleteBranches(
                        project.project_id,
                        merged.map((b) => b.name),
                      )
                    }
                  >
                    {t('settings.cleanup.deleteMerged')}
                  </Button>
                )}
              </div>
              {project.error && (
                <p role="alert" className="px-3 py-2 text-[12.5px] text-status-failed">
                  {project.error}
                </p>
              )}
              <ul aria-label={project.project_name} className="divide-y">
                {project.branches.map((branch) => (
                  <li key={branch.name} className="flex items-center gap-3 px-3 py-2 text-[13px]">
                    <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]">
                      {branch.name}
                    </span>
                    <span className="w-20 text-xs text-muted-foreground">
                      {branch.task_code ?? t('settings.cleanup.noTask')}
                    </span>
                    <span
                      className={cn(
                        'w-24 text-xs',
                        branch.in_use
                          ? 'text-status-running'
                          : branch.merged
                            ? 'text-status-done'
                            : 'text-status-waiting',
                      )}
                    >
                      {t(
                        branch.in_use
                          ? 'settings.cleanup.inUse'
                          : branch.merged
                            ? 'settings.cleanup.merged'
                            : 'settings.cleanup.unmerged',
                      )}
                    </span>
                    <span className="hidden w-36 text-xs text-muted-foreground sm:block">
                      {formatDateTime(branch.last_commit, now)}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={branch.in_use || remove.isPending}
                      onClick={() => onDelete(project.project_id, branch)}
                      aria-label={`${t('settings.cleanup.delete')} ${branch.name}`}
                    >
                      {t('settings.cleanup.delete')}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )
        })
      )}
      <ConfirmDialog
        open={unmerged !== null}
        onOpenChange={(open) => !open && setUnmerged(null)}
        title={t('settings.cleanup.forceTitle', { name: unmerged?.branch ?? '' })}
        description={t('settings.cleanup.forceDescription')}
        confirmLabel={t('settings.cleanup.forceConfirm')}
        destructive
        onConfirm={() => {
          if (unmerged) deleteBranches(unmerged.projectId, [unmerged.branch], true)
          setUnmerged(null)
        }}
      />
    </div>
  )
}
