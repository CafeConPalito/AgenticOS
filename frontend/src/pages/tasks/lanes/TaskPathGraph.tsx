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
import { useTranslation } from 'react-i18next'
import type { BranchDecision, Pipeline, Task } from '@/api/types'
import { cn } from '@/lib/utils'
import { taskPath, type StageState } from '../task-path'

interface PathData extends Record<string, unknown> {
  name: string
  agent: string | null
  state: StageState
}

type PathNode = Node<PathData, 'path'>

function PathStage({ data }: NodeProps<PathNode>) {
  const { t } = useTranslation()
  return (
    <div
      className={cn(
        'w-[170px] rounded-lg border px-2.5 py-1.5 text-[12.5px]',
        data.state === 'current' && 'border-status-running bg-status-running/10 font-medium',
        data.state === 'done' && 'border-sep text-muted-foreground',
        data.state === 'skipped' && 'border-dashed text-muted-foreground opacity-60',
        data.state === 'pending' && 'border-sep opacity-80',
      )}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <span className="block truncate">{data.name}</span>
      <span className="block truncate text-[11px] text-muted-foreground">
        {data.agent ?? t('pipeline.noAgent')} · {t(`tasks.lanes.stage.${data.state}`)}
      </span>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  )
}

const nodeTypes = { path: PathStage }

/** The pipeline with the path of a task marked: done, in progress, not taken, ahead. */
export function TaskPathGraph({
  pipeline,
  task,
  decisions,
}: {
  pipeline: Pipeline
  task: Task
  decisions: BranchDecision[]
}) {
  const { t } = useTranslation()
  const state = taskPath(pipeline, task, decisions)
  const nodes: PathNode[] = pipeline.stages.map((s) => ({
    id: s.id,
    type: 'path',
    position: { x: s.x, y: s.y },
    draggable: false,
    selectable: false,
    data: { name: s.name, agent: s.agent_name, state: state.get(s.id) ?? 'pending' },
  }))
  const forks = new Set(
    pipeline.links
      .filter((l) => pipeline.links.filter((x) => x.from_stage_id === l.from_stage_id).length > 1)
      .map((l) => l.id),
  )
  const edges: Edge[] = pipeline.links.map((l) => {
    const skipped = state.get(l.to_stage_id) === 'skipped'
    return {
      id: l.id,
      source: l.from_stage_id,
      target: l.to_stage_id,
      label: forks.has(l.id) ? l.name : undefined,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        stroke: skipped ? 'var(--border)' : 'var(--ring)',
        strokeDasharray: skipped ? '4 4' : undefined,
      },
      selectable: false,
    }
  })
  return (
    <div
      role="img"
      aria-label={t('tasks.lanes.pathLabel')}
      className="h-[220px] rounded-lg border bg-subtle"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        panOnScroll={false}
        fitView
        fitViewOptions={{ padding: 0.15, maxZoom: 1 }}
        minZoom={0.2}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} color="var(--border)" />
      </ReactFlow>
    </div>
  )
}
