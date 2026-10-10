import { useTranslation } from 'react-i18next'
import type { Project } from '@/api/types'

function Kpi({ label }: { label: string }) {
  const { t } = useTranslation()
  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-[22px] font-medium">{t('common.none')}</div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b py-2 last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right">{value}</span>
    </div>
  )
}

export function SummaryTab({ project }: { project: Project }) {
  const { t } = useTranslation()
  const git = project.git
  return (
    <div className="flex flex-col gap-4 px-6 pt-5 pb-8">
      <div className="grid grid-cols-4 gap-3">
        <Kpi label={t('projects.summary.openTasks')} />
        <Kpi label={t('projects.summary.running')} />
        <Kpi label={t('projects.summary.waiting')} />
        <Kpi label={t('projects.summary.cost')} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <section className="rounded-lg border bg-card px-4 py-3.5">
          <h2 className="mb-2 text-[14px] font-medium">{t('projects.summary.folder')}</h2>
          <Row
            label={t('projects.fields.path')}
            value={<span className="font-mono text-xs">{project.path}</span>}
          />
          <Row
            label={t('projects.summary.repo')}
            value={
              !project.folder_exists
                ? t('projects.folderMissing')
                : git === null
                  ? t('projects.summary.gitUnavailable')
                  : git.is_repo
                    ? t('projects.summary.isRepo')
                    : t('projects.summary.notRepo')
            }
          />
          {git?.is_repo && (
            <>
              <Row
                label={t('projects.summary.branch')}
                value={<span className="font-mono text-xs">{git.branch ?? t('common.none')}</span>}
              />
              <Row
                label={t('projects.summary.changes')}
                value={git.dirty ? t('projects.summary.dirty') : t('projects.summary.clean')}
              />
            </>
          )}
          <Row
            label={t('projects.fields.workspaceMode')}
            value={t(`projects.mode.${project.workspace_mode}`)}
          />
        </section>
        <section className="rounded-lg border bg-card px-4 py-3.5">
          <h2 className="mb-2 text-[14px] font-medium">{t('projects.summary.description')}</h2>
          <p className="text-pretty whitespace-pre-wrap text-muted-foreground">
            {project.description || t('projects.summary.noDescription')}
          </p>
        </section>
      </div>
    </div>
  )
}
