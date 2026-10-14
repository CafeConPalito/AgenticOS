import { FolderGit2, GitBranch, Plus, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useProjects } from '@/api/projects'
import type { Project } from '@/api/types'
import { EmptyState } from '@/components/EmptyState'
import { PageContainer, PageHeader } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { relativeTime } from '@/lib/time'

export default function ProjectsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data: projects, isPending } = useProjects()

  return (
    <PageContainer>
      <PageHeader
        title={t('projects.title')}
        subtitle={t('projects.subtitle')}
        actions={
          <Button
            onClick={() => navigate('/proyectos/nuevo')}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <Plus />
            {t('header.primary.newProject')}
          </Button>
        }
      />
      {isPending ? (
        <div aria-busy className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      ) : projects && projects.length > 0 ? (
        <ProjectsTable projects={projects} />
      ) : (
        <EmptyState
          icon={FolderGit2}
          title={t('pages.projects.emptyTitle')}
          description={t('pages.projects.emptyDescription')}
        >
          <Button
            onClick={() => navigate('/proyectos/nuevo')}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('header.primary.newProject')}
          </Button>
        </EmptyState>
      )}
    </PageContainer>
  )
}

export function GitLabel({ project }: { project: Project }) {
  const { t } = useTranslation()
  if (!project.folder_exists)
    return (
      <span className="inline-flex items-center gap-1.5 text-status-failed">
        <TriangleAlert className="size-3.5" />
        {t('projects.folderMissing')}
      </span>
    )
  if (!project.git?.is_repo)
    return (
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        <GitBranch className="size-3.5" />
        {t('common.none')}
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs">
      <GitBranch className="size-3.5 text-muted-foreground" />
      {project.git.branch ?? t('common.none')}
      {project.git.dirty && (
        <span
          title={t('projects.dirty')}
          aria-label={t('projects.dirty')}
          className="size-1.5 rounded-full bg-status-waiting"
        />
      )}
    </span>
  )
}

function ProjectsTable({ projects }: { projects: Project[] }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader className="bg-subtle">
          <TableRow className="hover:bg-transparent">
            <TableHead className="px-4">{t('projects.columns.project')}</TableHead>
            <TableHead>{t('projects.columns.folder')}</TableHead>
            <TableHead>{t('projects.columns.git')}</TableHead>
            <TableHead>{t('projects.columns.pipeline')}</TableHead>
            <TableHead className="text-right">{t('projects.columns.open')}</TableHead>
            <TableHead className="pr-4 text-right">{t('projects.columns.activity')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {projects.map((project) => {
            const open = () => navigate(`/proyectos/${project.id}/summary`)
            return (
              <TableRow
                key={project.id}
                tabIndex={0}
                aria-label={t('projects.open', { name: project.name })}
                onClick={open}
                onKeyDown={(e) => e.key === 'Enter' && open()}
                className="cursor-pointer"
              >
                <TableCell className="px-4 py-3.5">
                  <span className="inline-flex items-center gap-2.5 font-medium">
                    <span
                      className="size-2.5 rounded-[3px]"
                      style={{ background: project.color }}
                    />
                    {project.name}
                  </span>
                </TableCell>
                <TableCell className="max-w-[320px] truncate font-mono text-xs text-muted-foreground">
                  {project.path}
                </TableCell>
                <TableCell>
                  <GitLabel project={project} />
                </TableCell>
                <TableCell className="text-muted-foreground">{t('common.none')}</TableCell>
                <TableCell className="text-right font-mono">{t('common.none')}</TableCell>
                <TableCell className="pr-4 text-right text-muted-foreground">
                  {relativeTime(project.updated_at)}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
