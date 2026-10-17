import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useUpdateProject } from '@/api/projects'
import type { GitProjectFields, IntegrationModeSetting, OnApprove, Project } from '@/api/types'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/form-errors'

const MODES: IntegrationModeSetting[] = ['merge', 'squash', 'rebase']
const ON_APPROVE = ['none', 'integrate', 'integrate_push'] as const

/** How the project brings the branches of its tasks into their bases, what happens when a task
 * is approved and whether agents may use git freely. Each change is saved as it is made. */
export function GitSettingsSection({ project }: { project: Project }) {
  const { t } = useTranslation()
  const update = useUpdateProject(project.id)

  async function save(changes: Partial<GitProjectFields>) {
    try {
      await update.mutateAsync(changes)
      toast.success(t('common.saved'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <section aria-labelledby="git-settings-title" className="flex flex-col gap-3">
      <div>
        <h2 id="git-settings-title" className="font-medium">
          {t('projects.gitSettings.title')}
        </h2>
        <p className="text-sm text-muted-foreground">{t('projects.gitSettings.subtitle')}</p>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        {t('projects.gitSettings.mode')}
        <select
          value={project.integration_mode}
          onChange={(e) =>
            void save({ integration_mode: e.target.value as IntegrationModeSetting })
          }
          className="h-9 w-64 rounded-md border border-input bg-background px-2"
        >
          {MODES.map((mode) => (
            <option key={mode} value={mode}>
              {t(`tasks.integration.modes.${mode}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t('projects.gitSettings.onApprove')}
        <select
          value={project.on_approve === 'pull_request' ? 'none' : project.on_approve}
          onChange={(e) => void save({ on_approve: e.target.value as OnApprove })}
          className="h-9 w-64 rounded-md border border-input bg-background px-2"
        >
          {ON_APPROVE.map((value) => (
            <option key={value} value={value}>
              {t(`projects.gitSettings.onApproveOptions.${value}`)}
            </option>
          ))}
        </select>
      </label>
      <div className="flex items-start gap-3">
        <Switch
          id="agents-git"
          checked={project.agents_git_authorized}
          onCheckedChange={(checked) => void save({ agents_git_authorized: checked })}
        />
        <label htmlFor="agents-git" className="flex flex-col text-sm">
          {t('projects.gitSettings.agentsGit')}
          <span className="text-xs text-muted-foreground">
            {t('projects.gitSettings.agentsGitHelp')}
          </span>
        </label>
      </div>
    </section>
  )
}
