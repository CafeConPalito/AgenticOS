import { Copy, Sparkles, Workflow } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router'
import { usePipeline } from '@/api/pipelines'
import type { Project } from '@/api/types'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { ApplyDevelopmentDialog } from './pipeline/ApplyDevelopmentDialog'
import { CopyPipelineDialog } from './pipeline/CopyPipelineDialog'
import { PipelineEditor } from './pipeline/PipelineEditor'

/** The project's pipeline: a graph of stages, with forks where a task takes one or more
 * branches (phase 13). Without one, tasks go straight to the agent chosen for each; phase 24
 * starts it from «Desarrollo», a copy of another project's, the Architect or a blank one.
 * `?empezar=desarrollo|copiar|blanco` (from «Nuevo proyecto») opens that choice at once. */
export function PipelineTab({ project }: { project: Project }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const start = params.get('empezar')
  const pipeline = usePipeline(project.id)
  const [blank, setBlank] = useState(start === 'blanco')
  const [applying, setApplying] = useState(start === 'desarrollo')
  const [copying, setCopying] = useState(start === 'copiar')

  if (pipeline.isPending) return null
  if (!pipeline.data && !blank)
    return (
      <div className="px-6 pt-5 pb-8">
        <EmptyState
          icon={Workflow}
          title={t('pipeline.emptyTitle')}
          description={t('pipeline.emptyDescription')}
        >
          <div className="flex flex-wrap justify-center gap-2">
            <Button
              onClick={() => setApplying(true)}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              {t('pipeline.useTemplate')}
            </Button>
            <Button variant="outline" onClick={() => setCopying(true)}>
              <Copy />
              {t('pipeline.copy.button')}
            </Button>
            <Button
              variant="outline"
              onClick={() => void navigate(`/agentes/arquitecto?disenar=${project.id}`)}
            >
              <Sparkles />
              {t('pipeline.withArchitect')}
            </Button>
            <Button variant="outline" onClick={() => setBlank(true)}>
              {t('pipeline.startBlank')}
            </Button>
          </div>
        </EmptyState>
        <ApplyDevelopmentDialog open={applying} onOpenChange={setApplying} projectId={project.id} />
        <CopyPipelineDialog open={copying} onOpenChange={setCopying} projectId={project.id} />
      </div>
    )
  return (
    <PipelineEditor
      key={pipeline.data?.id ?? 'new'}
      project={project}
      pipeline={pipeline.data ?? null}
    />
  )
}
