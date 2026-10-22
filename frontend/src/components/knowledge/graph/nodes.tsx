import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { Bot, FileText, Globe, Image as ImageIcon, Unlink } from 'lucide-react'
import { memo } from 'react'
import { useTranslation } from 'react-i18next'
import type { GraphNode, KnowledgeScope } from '@/api/knowledge'
import { cn } from '@/lib/utils'
import { isDimmed, nodeKind, nodeSize, type NodeKind } from './model'

export const KIND_ICON: Record<NodeKind, typeof FileText> = {
  file: FileText,
  url: Globe,
  image: ImageIcon,
  agent: Bot,
  proposed: Bot,
  ghost: Unlink,
}

/** The colour of a level: the border of its documents. */
export const LEVEL_COLOR: Record<KnowledgeScope, string> = {
  general: 'var(--status-running)',
  project: 'var(--status-done)',
  agent: 'var(--status-review)',
}

export interface KnowledgeNodeData extends Record<string, unknown> {
  node: GraphNode
  /** A search is active: does this document answer it? `null`: no search. */
  matched: boolean | null
  /** The document the view is centred on (double click). */
  focused: boolean
  onOpen: (id: string) => void
  onFocus: (id: string) => void
}

export type KnowledgeFlowNode = Node<KnowledgeNodeData, 'doc'>

function DocumentNode({ data }: NodeProps<KnowledgeFlowNode>) {
  const { t } = useTranslation()
  const { node, matched, focused } = data
  const kind = nodeKind(node)
  const Icon = KIND_ICON[kind]
  const size = nodeSize(node.md_tokens)
  const dimmed = isDimmed(node)
  const color = node.scope ? LEVEL_COLOR[node.scope] : 'var(--muted-foreground)'
  const label = node.ghost
    ? t('knowledge.graph.node.ghost', { title: node.title })
    : t('knowledge.graph.node.open', { title: node.title })
  const open = () => {
    if (!node.ghost) data.onOpen(node.id)
  }
  return (
    <div
      className={cn(
        'flex w-[132px] flex-col items-center gap-1 outline-none',
        (dimmed || matched === false) && 'opacity-35',
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        isConnectable={false}
        style={{ top: size / 2, left: '50%', opacity: 0 }}
      />
      <div
        role="button"
        tabIndex={0}
        aria-label={label}
        data-kind={kind}
        data-matched={matched === null ? undefined : String(matched)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            open()
          }
        }}
        style={{ width: size, height: size, borderColor: color }}
        className={cn(
          'flex cursor-pointer items-center justify-center rounded-full border-2 bg-card shadow-card transition-shadow focus-visible:ring-[3px] focus-visible:ring-ring/50',
          kind === 'proposed' && 'border-dashed bg-subtle',
          kind === 'agent' && 'bg-primary-action/10',
          kind === 'ghost' && 'cursor-default border-dotted bg-transparent',
          matched === true && 'ring-[3px] ring-primary-action',
          focused && 'ring-[3px] ring-ring',
        )}
      >
        <Icon aria-hidden className="size-[45%] text-muted-foreground" />
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        isConnectable={false}
        style={{ top: size / 2, bottom: 'auto', left: '50%', opacity: 0 }}
      />
      <span
        className={cn(
          'line-clamp-2 text-center text-[11px] leading-tight text-balance',
          kind === 'ghost' && 'text-muted-foreground italic',
        )}
      >
        {node.title}
      </span>
    </div>
  )
}

export const nodeTypes = { doc: memo(DocumentNode) }
