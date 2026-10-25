import { FolderGit2, FolderOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Navigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { useOpenProjectFolder, useProject } from '@/api/projects'
import type { Project } from '@/api/types'
import { EmptyState } from '@/components/EmptyState'
import { ConnectionList } from '@/components/connections/ConnectionList'
import { KnowledgeLibrary } from '@/components/knowledge/KnowledgeLibrary'
import { FromClis } from '@/components/skills/SkillImportDialog'
import { SkillLibrary } from '@/components/skills/SkillLibrary'
import { PageContainer, RouteTabs } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/form-errors'
import { LaunchRunButton } from '@/pages/runs/LaunchRunDialog'
import { GitLabel } from './ProjectsPage'
import { GitTab } from './tabs/git/GitTab'
import { MemoryTab } from './tabs/MemoryTab'
import { PipelineTab } from './tabs/PipelineTab'
import { SettingsTab } from './tabs/SettingsTab'
import { SummaryTab } from './tabs/SummaryTab'
import { TasksTab } from './tabs/TasksTab'

const TABS = [
  'summary',
  'tasks',
  'pipeline',
  'git',
  'memory',
  'knowledge',
  'connections',
  'settings',
] as const
type Tab = (typeof TABS)[number]

export default function ProjectDetailPage() {
  const { projectId = '', tab } = useParams()
  const { t } = useTranslation()
  const { data: project, isPending, isError } = useProject(projectId)

  if (!TABS.includes(tab as Tab)) return <Navigate to={`/proyectos/${projectId}/summary`} replace />
  if (isPending)
    return (
      <PageContainer>
        <Skeleton aria-busy className="h-24 rounded-lg" />
      </PageContainer>
    )
  if (isError || !project)
    return (
      <PageContainer>
        <EmptyState icon={FolderGit2} title={t('projects.notFound')} />
      </PageContainer>
    )
  return <ProjectDetail key={project.id} project={project} tab={tab as Tab} />
}

function ProjectDetail({ project, tab }: { project: Project; tab: Tab }) {
  const { t } = useTranslation()
  const openFolder = useOpenProjectFolder()
  const tabs = TABS.map((id) => ({ id, label: t(`projects.tabs.${id}`) }))

  async function onOpenFolder() {
    try {
      await openFolder.mutateAsync(project.id)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex items-center gap-4 px-6 pt-[22px] pb-4">
        <span
          aria-hidden
          className="size-10 shrink-0 rounded-xl"
          style={{ background: project.color }}
        />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[20px] leading-[1.3] font-medium">{project.name}</h1>
          <div className="mt-1 flex items-center gap-3 text-[12.5px] text-muted-foreground">
            <span className="truncate font-mono text-xs">{project.path}</span>
            <GitLabel project={project} />
            <span>{t(`projects.mode.${project.workspace_mode}`)}</span>
          </div>
        </div>
        <Button
          variant="outline"
          onClick={() => void onOpenFolder()}
          disabled={!project.folder_exists || openFolder.isPending}
        >
          <FolderOpen />
          {t('projects.openFolder')}
        </Button>
        <LaunchRunButton projectId={project.id} disabled={!project.folder_exists} />
      </header>
      <RouteTabs base={`/proyectos/${project.id}`} tabs={tabs} label={t('projects.title')} />
      {tab === 'summary' && <SummaryTab project={project} />}
      {tab === 'tasks' && <TasksTab project={project} />}
      {tab === 'pipeline' && <PipelineTab project={project} />}
      {tab === 'git' && <GitTab project={project} />}
      {tab === 'memory' && <MemoryTab project={project} />}
      {tab === 'knowledge' && (
        <>
          <KnowledgeLibrary level={{ scope: 'project', projectId: project.id }} />
          <h2 className="px-6 pt-2 text-[16px] font-medium">{t('skills.title')}</h2>
          <SkillLibrary level={{ scope: 'project', projectId: project.id }} />
          <section className="flex flex-col gap-2 px-6 pb-8">
            <h3 className="text-[14px] font-medium">{t('skills.import.repoSkills')}</h3>
            <p className="text-[12.5px] text-muted-foreground">
              {t('skills.import.repoSkillsHint')}
            </p>
            <FromClis
              level={{ scope: 'project', projectId: project.id }}
              only={(item) => item.project_id === project.id}
            />
          </section>
        </>
      )}
      {tab === 'connections' && (
        <ConnectionList onlyLevel={{ scope: 'project', projectId: project.id }} />
      )}
      {tab === 'settings' && <SettingsTab project={project} />}
    </div>
  )
}
