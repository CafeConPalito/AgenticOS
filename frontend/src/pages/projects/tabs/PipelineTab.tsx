import { Workflow } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { usePipeline, usePipelineFromTemplate } from '@/api/pipelines'
import type { Project } from '@/api/types'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'
import { PipelineEditor } from './pipeline/PipelineEditor'

/** The project's pipeline: a graph of stages, with forks where a task takes one or more
 * branches (phase 13). Without one, tasks go straight to the agent chosen for each. */
export function PipelineTab({ project }: { project: Project }) {
  const { t } = useTranslation()
  const pipeline = usePipeline(project.id)
  const fromTemplate = usePipelineFromTemplate(project.id)
  const [blank, setBlank] = useState(false)

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
              onClick={() =>
                fromTemplate.mutate('web', { onError: (e) => toast.error(errorMessage(e)) })
              }
              disabled={fromTemplate.isPending}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              {t('pipeline.useTemplate')}
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                fromTemplate.mutate('web_split', { onError: (e) => toast.error(errorMessage(e)) })
              }
              disabled={fromTemplate.isPending}
            >
              {t('pipeline.useTemplateSplit')}
            </Button>
            <Button variant="outline" onClick={() => setBlank(true)}>
              {t('pipeline.startBlank')}
            </Button>
          </div>
        </EmptyState>
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
