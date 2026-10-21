import type { GraphEdge, GraphNode, KnowledgeGraph, KnowledgeScope } from '@/api/knowledge'

/** What a node looks like: where the document came from. */
export type NodeKind = 'file' | 'url' | 'image' | 'agent' | 'proposed' | 'ghost'

export function nodeKind(node: GraphNode): NodeKind {
  if (node.ghost) return 'ghost'
  if (node.review === 'proposed') return 'proposed'
  if (node.origin === 'agent') return 'agent'
  if (node.source_kind === 'url') return 'url'
  if (node.source_kind === 'image') return 'image'
  return 'file'
}

/** Switched off, failed or with the original lost: shown faded. */
export const isDimmed = (node: GraphNode) =>
  node.mode === 'off' ||
  node.status === 'failed' ||
  (node.presence !== null && node.presence !== 'ok')

/** Size by weight: from 24 px for a note to 64 px for a book. */
export function nodeSize(tokens: number): number {
  return Math.round(Math.max(24, Math.min(64, 18 + Math.sqrt(Math.max(tokens, 0)) * 1.1)))
}

export interface GraphFilters {
  level: 'all' | KnowledgeScope
  origin: 'all' | 'user' | 'agent'
  state: 'all' | 'pending' | 'problems'
  topic: 'all' | number
}

export const NO_FILTERS: GraphFilters = { level: 'all', origin: 'all', state: 'all', topic: 'all' }

export const isFiltered = (filters: GraphFilters) =>
  filters.level !== 'all' ||
  filters.origin !== 'all' ||
  filters.state !== 'all' ||
  filters.topic !== 'all'

function passes(node: GraphNode, filters: GraphFilters): boolean {
  if (filters.level !== 'all' && node.scope !== filters.level) return false
  if (filters.origin !== 'all' && node.origin !== filters.origin) return false
  if (filters.state === 'pending' && node.review !== 'proposed') return false
  if (filters.state === 'problems' && !isDimmed(node)) return false
  if (filters.topic !== 'all' && node.topic !== filters.topic) return false
  return true
}

/** The ids one link away from `id`, either way. */
export function neighborhood(edges: GraphEdge[], id: string): Set<string> {
  const near = new Set<string>([id])
  for (const edge of edges) {
    if (edge.source === id) near.add(edge.target)
    if (edge.target === id) near.add(edge.source)
  }
  return near
}

export interface Visible {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

/**
 * What the screen draws: the nodes that pass the filters (or, when a document is in focus, only
 * its neighbourhood), the links between them, and the «removed source» ghosts that still hang
 * from a document that is shown.
 */
export function visibleGraph(
  graph: KnowledgeGraph,
  filters: GraphFilters,
  focus: string | null,
): Visible {
  const near = focus ? neighborhood(graph.edges, focus) : null
  const real = graph.nodes.filter(
    (node) => !node.ghost && passes(node, filters) && (near === null || near.has(node.id)),
  )
  const shown = new Set(real.map((n) => n.id))
  const ghosts = graph.nodes.filter(
    (node) =>
      node.ghost &&
      graph.edges.some((e) => e.source === node.id && shown.has(e.target)) &&
      (near === null || near.has(node.id)),
  )
  for (const ghost of ghosts) shown.add(ghost.id)
  return {
    nodes: [...real, ...ghosts],
    edges: graph.edges.filter((e) => shown.has(e.source) && shown.has(e.target)),
  }
}
