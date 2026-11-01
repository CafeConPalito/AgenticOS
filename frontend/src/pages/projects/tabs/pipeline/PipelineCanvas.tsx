import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Eye, Flag, GitFork, Undo2 } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { Agent } from '@/api/types'
import { AgentAvatar } from '@/components/agentic/primitives'
import { cn } from '@/lib/utils'
import { newLink, type Draft } from './model'
import type { GraphIssueKeys } from './validate'

export type Selection = { kind: 'stage'; key: string } | { kind: 'link'; key: string } | null

interface StageData extends Record<string, unknown> {
  name: string
  agent: Agent | undefined
  fork: boolean
  review: boolean
  canReject: boolean
  invalid: boolean
  activeTasks: number
}

type StageNodeType = Node<StageData, 'stage'>

/** Phase 24: the «Fin» node of a stage's exit («Terminar aquí»). */
interface ExitData extends Record<string, unknown> {
  stage: string
  condition: string
  invalid: boolean
}

type ExitNodeType = Node<ExitData, 'exit'>
type CanvasNode = StageNodeType | ExitNodeType
const EXIT_PREFIX = 'exit:'

function ExitNode({ data, selected }: NodeProps<ExitNodeType>) {
  const { t } = useTranslation()
  const condition = data.condition.trim()
  return (
    <div
      role="img"
      aria-label={t('pipeline.exit.nodeLabel', {
        stage: data.stage,
        condition: condition || t('pipeline.exit.noCondition'),
      })}
      title={condition || t('pipeline.exit.noCondition')}
      className={cn(
        'flex max-w-[200px] items-center gap-1.5 rounded-full border border-dashed px-3 py-1.5 text-[12px] shadow-card bg-card-grad',
        selected ? 'border-ring ring-2 ring-ring/40' : 'border-sep',
        data.invalid && 'border-status-failed',
      )}
    >
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <Flag className="size-3.5 shrink-0" />
      <span className="font-medium">{t('pipeline.exit.node')}</span>
      <span className="truncate text-muted-foreground">
        {condition || t('pipeline.exit.noCondition')}
      </span>
    </div>
  )
}

function StageNode({ data, selected }: NodeProps<StageNodeType>) {
  const { t } = useTranslation()
  return (
    <div
      className={cn(
        'w-[230px] rounded-xl border p-3 shadow-card bg-card-grad',
        selected ? 'border-ring ring-2 ring-ring/40' : 'border-sep',
        data.invalid && 'border-status-failed',
      )}
    >
      <Handle type="target" position={Position.Left} />
      <div className="flex items-center gap-2">
        {data.agent ? (
          <AgentAvatar
            name={data.agent.name}
            color={data.agent.color}
            agentId={data.agent.id}
            size={22}
          />
        ) : (
          <span aria-hidden className="size-[22px] rounded-full border border-dashed" />
        )}
        <span className="min-w-0 flex-1 truncate text-[14px] font-medium">{data.name}</span>
      </div>
      <p className="mt-1 truncate text-[12px] text-muted-foreground">
        {data.agent?.name ?? t('pipeline.noAgent')}
      </p>
      {(data.fork || data.review || data.canReject) && (
        <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
          {data.fork && (
            <span className="inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5">
              <GitFork className="size-3" />
              {t('pipeline.badgeFork')}
            </span>
          )}
          {data.review && (
            <span className="inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5">
              <Eye className="size-3" />
              {t('pipeline.badgeReview')}
            </span>
          )}
          {data.canReject && (
            <span className="inline-flex items-center gap-1 rounded-full border border-status-failed px-1.5 py-0.5 text-status-failed">
              <Undo2 className="size-3" />
              {t('pipeline.badgeReject')}
            </span>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} />
      {/* Anchors of the rejection arrows (drawn from the stage's panel, not by dragging). */}
      <Handle
        id="reject-out"
        type="source"
        position={Position.Bottom}
        isConnectable={false}
        style={{ left: '30%' }}
      />
      <Handle
        id="reject-in"
        type="target"
        position={Position.Bottom}
        isConnectable={false}
        style={{ left: '70%' }}
      />
      {/* Phase 24: where the «Fin» node of its exit hangs. */}
      <Handle
        id="exit-out"
        type="source"
        position={Position.Bottom}
        isConnectable={false}
        style={{ left: '50%' }}
      />
    </div>
  )
}

const nodeTypes = { stage: StageNode, exit: ExitNode }
const REJECT_PREFIX = 'reject:'

interface CanvasProps {
  draft: Draft
  agents: Agent[]
  issues: GraphIssueKeys[]
  selection: Selection
  onSelect: (selection: Selection) => void
  onChange: (update: (draft: Draft) => Draft) => void
  onRemoveStage: (key: string) => void
}

export function PipelineCanvas({
  draft,
  agents,
  issues,
  selection,
  onSelect,
  onChange,
  onRemoveStage,
}: CanvasProps) {
  const { t } = useTranslation()
  const outgoing = useMemo(() => {
    const count = new Map<string, number>()
    for (const l of draft.links) count.set(l.source, (count.get(l.source) ?? 0) + 1)
    return count
  }, [draft.links])

  const exitIssues = new Set(
    issues.filter((i) => i.code.startsWith('exit_') && i.stage).map((i) => i.stage as string),
  )
  const stageNodes: StageNodeType[] = draft.stages.map((s) => ({
    id: s.key,
    type: 'stage',
    position: { x: s.x, y: s.y },
    selected: selection?.kind === 'stage' && selection.key === s.key,
    deletable: s.activeTasks === 0 && draft.stages.length > 1,
    data: {
      name: s.name,
      agent: agents.find((a) => a.id === s.agentId),
      fork: (outgoing.get(s.key) ?? 0) > 1,
      review: s.requiresReview,
      canReject: Boolean(s.rejectTo),
      invalid: issues.some((i) => i.stage === s.key),
      activeTasks: s.activeTasks,
    },
  }))
  const exitNodes: ExitNodeType[] = draft.stages.flatMap((s) =>
    s.exit
      ? [
          {
            id: `${EXIT_PREFIX}${s.key}`,
            type: 'exit' as const,
            position: { x: s.exit.x, y: s.exit.y },
            selected: false,
            data: { stage: s.name, condition: s.exit.condition, invalid: exitIssues.has(s.key) },
          },
        ]
      : [],
  )
  const nodes: CanvasNode[] = [...stageNodes, ...exitNodes]

  const edges: Edge[] = [
    ...draft.links.map((l): Edge => {
      const branch = (outgoing.get(l.source) ?? 0) > 1
      const bad = issues.some((i) => i.link === l.key)
      return {
        id: l.key,
        source: l.source,
        target: l.target,
        selected: selection?.kind === 'link' && selection.key === l.key,
        label: branch ? l.name || undefined : undefined,
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: bad ? 'var(--status-failed)' : 'var(--ring)', strokeWidth: 2 },
        labelBgPadding: [6, 3],
        labelBgBorderRadius: 6,
      }
    }),
    ...draft.stages.flatMap((s) =>
      [s.rejectTo, ...s.rejectAlso]
        .filter((k): k is string => Boolean(k))
        .map((target): Edge => ({
          id: `${REJECT_PREFIX}${s.key}:${target}`,
          source: s.key,
          sourceHandle: 'reject-out',
          target,
          targetHandle: 'reject-in',
          type: 'smoothstep',
          label: t('pipeline.edgeRejects'),
          markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--status-failed)' },
          style: { stroke: 'var(--status-failed)', strokeDasharray: '6 4' },
          deletable: false,
          selectable: false,
        })),
    ),
    ...draft.stages.flatMap((s) =>
      s.exit
        ? [
            {
              id: `${EXIT_PREFIX}edge:${s.key}`,
              source: s.key,
              sourceHandle: 'exit-out',
              target: `${EXIT_PREFIX}${s.key}`,
              markerEnd: { type: MarkerType.ArrowClosed },
              style: { stroke: 'var(--muted-foreground)', strokeDasharray: '4 4' },
              deletable: false,
              selectable: false,
            } satisfies Edge,
          ]
        : [],
    ),
  ]

  function onNodesChange(changes: NodeChange<CanvasNode>[]) {
    for (const change of changes) {
      // A «Fin» node belongs to its stage: moving it moves the exit, picking it picks the stage.
      const exitOf =
        'id' in change && change.id.startsWith(EXIT_PREFIX)
          ? change.id.slice(EXIT_PREFIX.length)
          : null
      if (change.type === 'position' && change.position) {
        const { x, y } = change.position
        onChange((d) => ({
          ...d,
          stages: d.stages.map((s) =>
            exitOf
              ? s.key === exitOf && s.exit
                ? { ...s, exit: { ...s.exit, x, y } }
                : s
              : s.key === change.id
                ? { ...s, x, y }
                : s,
          ),
        }))
      } else if (change.type === 'select' && change.selected) {
        onSelect({ kind: 'stage', key: exitOf ?? change.id })
      }
    }
  }

  function onEdgesChange(changes: EdgeChange[]) {
    for (const change of changes)
      if (change.type === 'select' && change.selected && !change.id.startsWith(REJECT_PREFIX))
        onSelect({ kind: 'link', key: change.id })
  }

  function onConnect(c: Connection) {
    if (!c.source || !c.target || c.source === c.target) return
    onChange((d) =>
      d.links.some((l) => l.source === c.source && l.target === c.target)
        ? d
        : {
            ...d,
            links: [
              ...d.links,
              newLink(c.source, c.target, d.stages.find((s) => s.key === c.target)?.name ?? ''),
            ],
          },
    )
  }

  return (
    <div
      className="h-[460px] rounded-xl border bg-subtle"
      aria-label={t('pipeline.canvas')}
      data-testid="pipeline-canvas"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodesDelete={(deleted) =>
          deleted.forEach((n) =>
            n.id.startsWith(EXIT_PREFIX)
              ? onChange((d) => ({
                  ...d,
                  stages: d.stages.map((s) =>
                    s.key === n.id.slice(EXIT_PREFIX.length) ? { ...s, exit: null } : s,
                  ),
                }))
              : onRemoveStage(n.id),
          )
        }
        onEdgesDelete={(deleted) =>
          onChange((d) => ({
            ...d,
            links: d.links.filter((l) => !deleted.some((e) => e.id === l.key)),
          }))
        }
        onPaneClick={() => onSelect(null)}
        deleteKeyCode={['Delete']}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        minZoom={0.3}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} color="var(--border)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
