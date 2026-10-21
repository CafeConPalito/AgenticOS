import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Network, Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useKnowledgeGraph,
  useSearchKnowledge,
  type GraphEdge,
  type KnowledgeGraph as GraphData,
} from '@/api/knowledge'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/form-errors'
import { isFiltered, nodeSize, NO_FILTERS, visibleGraph, type GraphFilters } from './model'
import { nodeTypes, type KnowledgeFlowNode } from './nodes'
import { useGraphLayout } from './use-layout'
import { GraphLegend } from './GraphLegend'

const WEAK_BELOW_ZOOM = 0.55
const WEAK_WEIGHT = 0.5
const NODE_WIDTH = 132
// Up to here every node is drawn; beyond, only the ones in view (the canvas has to stay fluid).
const LARGE = 80

export function flowEdge(edge: GraphEdge, zoom: number): Edge {
  const derived = edge.kind === 'derived'
  return {
    id: `${edge.kind}:${edge.source}:${edge.target}`,
    source: edge.source,
    target: edge.target,
    type: 'straight',
    // Zoomed out, the weak guesses are noise: only facts and strong links stay.
    hidden: !derived && zoom < WEAK_BELOW_ZOOM && edge.weight < WEAK_WEIGHT,
    markerEnd: derived
      ? { type: MarkerType.ArrowClosed, width: 14, height: 14, color: 'var(--foreground)' }
      : undefined,
    style: derived
      ? { stroke: 'var(--foreground)', strokeWidth: 1.6, opacity: 0.75 }
      : {
          stroke: 'var(--muted-foreground)',
          strokeWidth: 1 + edge.weight * 3,
          strokeDasharray: '5 5',
          opacity: 0.6,
        },
    focusable: false,
  }
}

function Filters({
  graph,
  filters,
  onChange,
}: {
  graph: GraphData
  filters: GraphFilters
  onChange: (next: GraphFilters) => void
}) {
  const { t } = useTranslation()
  const f = 'knowledge.graph.filters'
  const select = (
    label: string,
    value: string,
    options: { value: string; label: string }[],
    set: (value: string) => void,
  ) => (
    <Select value={value} onValueChange={set}>
      <SelectTrigger aria-label={label} className="h-8 w-[190px] text-[12.5px]">
        <span className="text-muted-foreground">{label}:</span>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
  return (
    <div role="group" aria-label={t(`${f}.label`)} className="flex flex-wrap items-center gap-2">
      {select(
        t(`${f}.level`),
        filters.level,
        (['all', 'general', 'project', 'agent'] as const).map((v) => ({
          value: v,
          label: t(`${f}.${v}`),
        })),
        (level) => onChange({ ...filters, level: level as GraphFilters['level'] }),
      )}
      {select(
        t(`${f}.origin`),
        filters.origin,
        [
          { value: 'all', label: t(`${f}.all`) },
          { value: 'user', label: t(`${f}.user`) },
          { value: 'agent', label: t(`${f}.byAgent`) },
        ],
        (origin) => onChange({ ...filters, origin: origin as GraphFilters['origin'] }),
      )}
      {select(
        t(`${f}.state`),
        filters.state,
        [
          { value: 'all', label: t(`${f}.all`) },
          { value: 'pending', label: t(`${f}.pending`) },
          { value: 'problems', label: t(`${f}.problems`) },
        ],
        (state) => onChange({ ...filters, state: state as GraphFilters['state'] }),
      )}
      {graph.topics.length > 0 &&
        select(
          t(`${f}.topic`),
          String(filters.topic),
          [
            { value: 'all', label: t(`${f}.all`) },
            ...graph.topics.map((topic) => ({
              value: String(topic.id),
              label: topic.loose ? t('knowledge.graph.topics.loose') : topic.name,
            })),
          ],
          (topic) => onChange({ ...filters, topic: topic === 'all' ? 'all' : Number(topic) }),
        )}
      {isFiltered(filters) && (
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange(NO_FILTERS)}>
          {t(`${f}.reset`)}
        </Button>
      )}
    </div>
  )
}

function Canvas({
  graph,
  filters,
  focus,
  matches,
  onOpen,
  onFocus,
}: {
  graph: GraphData
  filters: GraphFilters
  focus: string | null
  matches: Set<string> | null
  onOpen: (id: string) => void
  onFocus: (id: string | null) => void
}) {
  const { t } = useTranslation()
  const flow = useReactFlow()
  const [zoom, setZoom] = useState(1)
  const visible = useMemo(() => visibleGraph(graph, filters, focus), [graph, filters, focus])
  const layout = useGraphLayout(
    useMemo(
      () =>
        visible.nodes.map((n) => ({
          id: n.id,
          topic: n.topic,
          radius: nodeSize(n.md_tokens) / 2 + 22,
        })),
      [visible.nodes],
    ),
    useMemo(
      () =>
        visible.edges.map((e) => ({
          source: e.source,
          target: e.target,
          weight: e.kind === 'derived' ? 0.9 : e.weight,
        })),
      [visible.edges],
    ),
  )

  const nodes = useMemo<KnowledgeFlowNode[]>(
    () =>
      visible.nodes.map((node) => {
        const place = layout.positions[node.id] ?? { x: 0, y: 0 }
        return {
          id: node.id,
          type: 'doc',
          position: { x: place.x - NODE_WIDTH / 2, y: place.y - nodeSize(node.md_tokens) / 2 },
          draggable: false,
          data: {
            node,
            matched: matches === null ? null : matches.has(node.id),
            focused: focus === node.id,
            onOpen,
            onFocus,
          },
        }
      }),
    [visible.nodes, layout.positions, matches, focus, onOpen, onFocus],
  )
  const edges = useMemo(() => visible.edges.map((e) => flowEdge(e, zoom)), [visible.edges, zoom])

  // When the layout has settled (or the set of documents changed), show all of it.
  const settled = !layout.working && nodes.length > 0
  const count = nodes.length
  useEffect(() => {
    if (settled) void flow.fitView({ padding: 0.2 })
  }, [settled, count, flow])

  return (
    <div
      role="group"
      aria-label={t('knowledge.graph.canvas')}
      className="relative h-[min(68vh,640px)] min-h-[360px] overflow-hidden rounded-xl border bg-card"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onMove={(_, viewport) => setZoom(viewport.zoom)}
        nodesConnectable={false}
        nodesDraggable={false}
        // A click opens the document, a double click looks at its neighbourhood (a keyboard goes
        // through the node itself).
        onNodeClick={(_, clicked) => {
          if (!clicked.data.node.ghost) onOpen(clicked.id)
        }}
        onNodeDoubleClick={(_, clicked) => onFocus(clicked.id)}
        elementsSelectable={false}
        zoomOnDoubleClick={false}
        minZoom={0.1}
        maxZoom={2}
        onlyRenderVisibleElements={nodes.length > LARGE}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
      {layout.working && (
        <p className="absolute top-2 left-3 text-[12px] text-muted-foreground">
          {t('knowledge.graph.layouting')}
        </p>
      )}
      <p className="absolute right-3 bottom-2 text-[11px] text-muted-foreground">
        {t('knowledge.graph.weak')}
      </p>
    </div>
  )
}

/**
 * The library as a graph: one node per document (its look says where it came from), «derived
 * from» and «related» links, filters, a search that highlights what answers a question, a click
 * to open a document and a double click to look only at its neighbourhood.
 */
export function KnowledgeGraph({
  projectId,
  agentId,
  onOpen,
}: {
  projectId?: string
  agentId?: string
  onOpen: (id: string) => void
}) {
  const { t } = useTranslation()
  const [everything, setEverything] = useState(false)
  const [filters, setFilters] = useState<GraphFilters>(NO_FILTERS)
  const [focus, setFocus] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<Set<string> | null>(null)
  const graph = useKnowledgeGraph(everything ? { everything: true } : { projectId, agentId })
  const search = useSearchKnowledge()

  async function highlight(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    try {
      const result = await search.mutateAsync({ query: query.trim(), projectId, agentId })
      setMatches(new Set(result.hits.map((hit) => hit.doc_id)))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const focusedTitle = graph.data?.nodes.find((n) => n.id === focus)?.title ?? ''
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Switch
            id="graph-everything"
            checked={everything}
            onCheckedChange={(value) => {
              setEverything(value)
              setFocus(null)
              setMatches(null)
            }}
            aria-label={t('knowledge.graph.scope.all')}
          />
          <label htmlFor="graph-everything" className="text-[13px]">
            {t('knowledge.graph.scope.all')}
          </label>
        </div>
        <form onSubmit={(e) => void highlight(e)} className="flex flex-1 gap-2 sm:max-w-[520px]">
          <Input
            aria-label={t('knowledge.graph.search.label')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('knowledge.graph.search.placeholder')}
          />
          <Button type="submit" variant="outline" disabled={!query.trim() || search.isPending}>
            <Search />
            {t('knowledge.graph.search.run')}
          </Button>
          {matches !== null && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setMatches(null)
                setQuery('')
              }}
            >
              <X />
              {t('knowledge.graph.search.clear')}
            </Button>
          )}
        </form>
      </div>

      {graph.isPending ? (
        <Skeleton aria-busy className="h-72 rounded-xl" />
      ) : graph.isError ? (
        <p role="alert" className="text-status-failed">
          {t('knowledge.loadFailed')}
        </p>
      ) : graph.data.nodes.length === 0 ? (
        <EmptyState
          icon={Network}
          title={t('knowledge.graph.title')}
          description={t('knowledge.graph.empty')}
        />
      ) : (
        <>
          <Filters graph={graph.data} filters={filters} onChange={setFilters} />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-muted-foreground">
            <span>
              {t('knowledge.graph.summary', {
                nodes: graph.data.nodes.length,
                edges: graph.data.edges.length,
              })}
            </span>
            {matches !== null && (
              <span role="status">
                {matches.size > 0
                  ? t('knowledge.graph.search.found', { count: matches.size })
                  : t('knowledge.graph.search.none')}
              </span>
            )}
            {focus && (
              <span className="flex items-center gap-2">
                {t('knowledge.graph.focused', { title: focusedTitle })}
                <Button type="button" variant="outline" size="sm" onClick={() => setFocus(null)}>
                  {t('knowledge.graph.unfocus')}
                </Button>
              </span>
            )}
          </div>
          <ReactFlowProvider>
            <Canvas
              graph={graph.data}
              filters={filters}
              focus={focus}
              matches={matches}
              onOpen={onOpen}
              onFocus={setFocus}
            />
          </ReactFlowProvider>
          <GraphLegend graph={graph.data} />
        </>
      )}
    </section>
  )
}
