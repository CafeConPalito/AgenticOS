import { GitBranch } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { useGitOverview } from '@/api/git'
import type { Project } from '@/api/types'
import { EmptyState } from '@/components/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { RepoView, SECTIONS, type Section } from './RepoView'
import { ReposOverview } from './ReposOverview'
import { useGitEvents } from './use-git-events'

/** The Git tab of a project: its repositories (one view each) and what applies to all of them. */
export function GitTab({ project }: { project: Project }) {
  const { t } = useTranslation()
  const overview = useGitOverview(project.id)
  const [params, setParams] = useSearchParams()
  useGitEvents()

  if (overview.isPending) return <Skeleton aria-busy className="m-6 h-40 rounded-lg" />
  if (overview.isError)
    return (
      <p role="alert" className="px-6 py-4 text-[13px] text-status-failed">
        {t('git.error')}
      </p>
    )

  const repos = overview.data
  if (repos.length === 0)
    return (
      <div className="px-6 py-8">
        <EmptyState
          icon={GitBranch}
          title={t('git.none.title')}
          description={t('git.none.description')}
        >
          <Link
            to={`/proyectos/${project.id}/settings`}
            className="text-[13px] text-primary hover:underline"
          >
            {t('git.none.action')}
          </Link>
        </EmptyState>
      </div>
    )

  const selected = repos.find((r) => r.repo_id === params.get('repo')) ?? repos[0]
  const asked = params.get('section') as Section | null
  const section = asked && SECTIONS.includes(asked) ? asked : 'changes'
  const change = (next: { repo?: string; section?: Section }) =>
    setParams(
      (previous) => {
        const merged = new URLSearchParams(previous)
        if (next.repo) merged.set('repo', next.repo)
        if (next.section) merged.set('section', next.section)
        return merged
      },
      { replace: true },
    )

  return (
    <div
      className={repos.length > 1 ? 'grid grid-cols-[300px_1fr]' : 'flex flex-col'}
      data-testid="git-tab"
    >
      {repos.length > 1 && (
        <ReposOverview
          projectId={project.id}
          repos={repos}
          selected={selected.repo_id}
          onSelect={(repo) => change({ repo })}
        />
      )}
      <RepoView
        key={selected.repo_id}
        repo={selected}
        section={section}
        onSection={(next) => change({ section: next })}
      />
    </div>
  )
}
