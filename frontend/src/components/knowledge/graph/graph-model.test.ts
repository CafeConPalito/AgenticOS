import type { GraphEdge, GraphNode, KnowledgeGraph } from '@/api/knowledge'
import { flowEdge } from './KnowledgeGraph'
import { layoutGraph, topicAnchors, type LayoutLink, type LayoutNode } from './layout'
import { isDimmed, neighborhood, nodeKind, nodeSize, NO_FILTERS, visibleGraph } from './model'

function node(id: string, overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id,
    title: id,
    summary: '',
    ghost: false,
    origin: 'user',
    source_kind: 'file',
    review: 'none',
    scope: 'general',
    project_id: null,
    agent_id: null,
    mode: 'auto',
    status: 'ready',
    presence: 'ok',
    md_tokens: 1000,
    topic: 0,
    ...overrides,
  }
}

const edge = (source: string, target: string, kind: GraphEdge['kind'] = 'related', weight = 0.6) =>
  ({ kind, source, target, weight }) satisfies GraphEdge

function graphOf(nodes: GraphNode[], edges: GraphEdge[]): KnowledgeGraph {
  return { version: 1, nodes, edges, topics: [] }
}

describe('what a node looks like', () => {
  it('tells where the document came from', () => {
    expect(nodeKind(node('a'))).toBe('file')
    expect(nodeKind(node('a', { source_kind: 'url' }))).toBe('url')
    expect(nodeKind(node('a', { source_kind: 'image' }))).toBe('image')
    expect(nodeKind(node('a', { origin: 'agent', source_kind: 'markdown' }))).toBe('agent')
    expect(nodeKind(node('a', { origin: 'agent', review: 'proposed' }))).toBe('proposed')
    expect(nodeKind(node('a', { ghost: true }))).toBe('ghost')
  })

  it('grows with the weight of the document, within limits', () => {
    expect(nodeSize(0)).toBe(24)
    expect(nodeSize(100)).toBeLessThan(nodeSize(10_000))
    expect(nodeSize(100_000_000)).toBe(64)
  })

  it('fades what is switched off, failed or has lost its original', () => {
    expect(isDimmed(node('a'))).toBe(false)
    expect(isDimmed(node('a', { mode: 'off' }))).toBe(true)
    expect(isDimmed(node('a', { status: 'failed' }))).toBe(true)
    expect(isDimmed(node('a', { presence: 'missing' }))).toBe(true)
  })
})

describe('which nodes are drawn', () => {
  const data = graphOf(
    [
      node('pdf'),
      node('guide', { origin: 'agent', source_kind: 'markdown', topic: 0 }),
      node('draft', { origin: 'agent', review: 'proposed', topic: 0 }),
      node('mine', { scope: 'project', project_id: 'p1', topic: 1 }),
      node('old', { mode: 'off', topic: 1 }),
      node('removed:1', { ghost: true, title: 'Borrado', scope: null }),
    ],
    [
      edge('pdf', 'guide', 'derived', 1),
      edge('guide', 'draft', 'derived', 1),
      edge('pdf', 'mine'),
      edge('removed:1', 'draft', 'derived', 1),
    ],
  )
  const ids = (found: ReturnType<typeof visibleGraph>) => found.nodes.map((n) => n.id).sort()

  it('draws everything without filters', () => {
    expect(ids(visibleGraph(data, NO_FILTERS, null))).toEqual(
      ['draft', 'guide', 'mine', 'old', 'pdf', 'removed:1'].sort(),
    )
  })

  it('filters by level, origin, state and topic', () => {
    expect(ids(visibleGraph(data, { ...NO_FILTERS, level: 'project' }, null))).toEqual(['mine'])
    expect(ids(visibleGraph(data, { ...NO_FILTERS, origin: 'agent' }, null))).toEqual(
      ['draft', 'guide', 'removed:1'].sort(),
    )
    expect(ids(visibleGraph(data, { ...NO_FILTERS, state: 'pending' }, null))).toEqual([
      'draft',
      'removed:1',
    ])
    expect(ids(visibleGraph(data, { ...NO_FILTERS, state: 'problems' }, null))).toEqual(['old'])
    expect(ids(visibleGraph(data, { ...NO_FILTERS, topic: 1 }, null))).toEqual(['mine', 'old'])
  })

  it('keeps a ghost only while something it hangs from is shown', () => {
    expect(ids(visibleGraph(data, { ...NO_FILTERS, origin: 'user' }, null))).not.toContain(
      'removed:1',
    )
  })

  it('draws only the links between drawn nodes', () => {
    const found = visibleGraph(data, { ...NO_FILTERS, level: 'general', topic: 0 }, null)
    expect(found.edges.map((e) => `${e.source}>${e.target}`).sort()).toEqual([
      'guide>draft',
      'pdf>guide',
      'removed:1>draft',
    ])
  })

  it('looks at the neighbourhood of a document in focus', () => {
    expect(ids(visibleGraph(data, NO_FILTERS, 'guide'))).toEqual(['draft', 'guide', 'pdf'])
    expect(neighborhood(data.edges, 'pdf')).toEqual(new Set(['pdf', 'guide', 'mine']))
  })
})

describe('the lines between documents', () => {
  it('draws «derived from» solid with an arrow and «related» dashed, thicker if stronger', () => {
    const derived = flowEdge(edge('a', 'b', 'derived', 1), 1)
    expect(derived.markerEnd).toBeDefined()
    expect(derived.style?.strokeDasharray).toBeUndefined()
    const weak = flowEdge(edge('a', 'b', 'related', 0.2), 1)
    const strong = flowEdge(edge('a', 'b', 'related', 0.9), 1)
    expect(weak.style?.strokeDasharray).toBe('5 5')
    expect(weak.markerEnd).toBeUndefined()
    expect(Number(strong.style?.strokeWidth)).toBeGreaterThan(Number(weak.style?.strokeWidth))
  })

  it('hides weak guesses when zoomed out, never the facts or the strong links', () => {
    expect(flowEdge(edge('a', 'b', 'related', 0.2), 0.3).hidden).toBe(true)
    expect(flowEdge(edge('a', 'b', 'related', 0.2), 1).hidden).toBe(false)
    expect(flowEdge(edge('a', 'b', 'related', 0.8), 0.3).hidden).toBe(false)
    expect(flowEdge(edge('a', 'b', 'derived', 1), 0.3).hidden).toBe(false)
  })
})

describe('the force layout', () => {
  function ring(count: number, topics: number, extra = 0): [LayoutNode[], LayoutLink[]] {
    const nodes = Array.from({ length: count }, (_, i) => ({
      id: `n${i}`,
      topic: i % topics,
      radius: 30,
    }))
    const links: LayoutLink[] = []
    for (let i = 0; i < count; i++) {
      // A neighbour of the same topic, so the topics are dense inside and sparse outside.
      links.push({ source: `n${i}`, target: `n${(i + topics) % count}`, weight: 0.6 })
    }
    for (let i = 0; i < extra; i++)
      links.push({
        source: `n${(i * 7) % count}`,
        target: `n${(i * 13 + 5) % count}`,
        weight: 0.3,
      })
    return [nodes, links]
  }

  it('gives the same positions for the same graph', () => {
    const [nodes, links] = ring(40, 4)
    expect(layoutGraph(nodes, links)).toEqual(layoutGraph(nodes, links))
  })

  it('gathers the documents of a topic and tells the topics apart', () => {
    const [nodes, links] = ring(60, 3)
    const where = layoutGraph(nodes, links)
    const distance = (a: string, b: string) =>
      Math.hypot(where[a].x - where[b].x, where[a].y - where[b].y)
    let within = 0
    let between = 0
    let w = 0
    let b = 0
    for (let i = 0; i < 60; i++)
      for (let j = i + 1; j < 60; j++) {
        if (nodes[i].topic === nodes[j].topic) {
          within += distance(`n${i}`, `n${j}`)
          w++
        } else {
          between += distance(`n${i}`, `n${j}`)
          b++
        }
      }
    expect(within / w).toBeLessThan(between / b)
  })

  it('reports its progress and ends with the final positions', () => {
    const [nodes, links] = ring(20, 2)
    const seen: number[] = []
    const final = layoutGraph(nodes, links, (p) => seen.push(Object.keys(p).length))
    expect(seen.length).toBeGreaterThan(1)
    expect(Object.keys(final)).toHaveLength(20)
  })

  it('ignores links to documents that are not there and survives an empty graph', () => {
    expect(layoutGraph([], [])).toEqual({})
    const where = layoutGraph(
      [{ id: 'a', topic: null, radius: 10 }],
      [{ source: 'a', target: 'ghost', weight: 1 }],
    )
    expect(Object.keys(where)).toEqual(['a'])
  })

  it('spreads the topics on a ring', () => {
    const anchors = topicAnchors([0, 1, 2, 3])
    expect(anchors.size).toBe(4)
    expect(topicAnchors([5]).get(5)).toEqual({ x: 0, y: 0 })
  })

  it('lays out 300 documents and 1 000 links well within a second or two', () => {
    const [nodes, links] = ring(300, 12, 700)
    expect(links.length).toBe(1000)
    const started = performance.now()
    const where = layoutGraph(nodes, links)
    const elapsed = performance.now() - started
    expect(Object.keys(where)).toHaveLength(300)
    // Measured 330 ms on the development machine; the margin is for a slow CI.
    expect(elapsed).toBeLessThan(3000)
  })
})
