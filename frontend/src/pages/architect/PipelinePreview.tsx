import {
  Background,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Eye } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { SheetPipeline } from '@/api/architect'
import { cn } from '@/lib/utils'

interface StageData extends Record<string, unknown> {
  name: string
  agent: string
  review: boolean
  changed: boolean
}

type StageNodeType = Node<StageData, 'stage'>

function StageNode({ data }: NodeProps<StageNodeType>) {
  const { t } = useTranslation()
  return (
    <div
      className={cn(
        'w-[200px] rounded-xl border p-3 shadow-card bg-card-grad',
        data.changed ? 'border-status-review ring-1 ring-status-review' : 'border-sep',
      )}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <p className="truncate text-[13.5px] font-medium">{data.name}</p>
      <p className="mt-0.5 truncate text-[12px] text-muted-foreground">
        {data.agent || t('pipeline.noAgent')}
      </p>
      {data.review && (
        <span className="mt-1.5 inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[11px] text-muted-foreground">
          <Eye className="size-3" aria-hidden />
          {t('pipeline.badgeReview')}
        </span>
      )}
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  )
}

const nodeTypes = { stage: StageNode }

/** The pipeline of a sheet or proposal drawn read-only, stages where the editor would put
 * them (`layout`, by stage index), with the ones that change marked. */
export function PipelinePreview({
  pipeline,
  layout,
  agentNames,
  changed = [],
}: {
  pipeline: SheetPipeline
  layout?: Record<string, [number, number]>
  /** Names of the agents by id or `ref:<ref>`. */
  agentNames: Record<string, string>
  /** Names of the stages that are added or modified. */
  changed?: string[]
}) {
  const { t } = useTranslation()
  const nodes: StageNodeType[] = pipeline.stages.map((stage, index) => ({
    id: String(index),
    type: 'stage',
    position: {
      x: layout?.[String(index)]?.[0] ?? index * 260,
      y: layout?.[String(index)]?.[1] ?? 0,
    },
    draggable: false,
    selectable: false,
    data: {
      name: stage.name,
      agent: agentNames[stage.agent ?? ''] ?? '',
      review: Boolean(stage.requires_review),
      changed: changed.includes(stage.name),
    },
  }))
  const links =
    pipeline.links ?? pipeline.stages.slice(1).map((_, i) => ({ source: i, target: i + 1 }))
  const edges: Edge[] = links.map((link, i) => ({
    id: `l${i}`,
    source: String(link.source),
    target: String(link.target),
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: 'var(--ring)', strokeWidth: 2 },
  }))
  return (
    <div
      className="h-[320px] rounded-xl border bg-subtle"
      aria-label={t('architect.pipelinePreview')}
      data-testid="pipeline-preview"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        minZoom={0.3}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} color="var(--border)" />
      </ReactFlow>
    </div>
  )
}
