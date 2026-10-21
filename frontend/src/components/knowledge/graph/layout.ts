import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force'

export interface LayoutNode {
  id: string
  /** The topic the document belongs to; nodes of one topic are pulled together. */
  topic: number | null
  /** Space the node takes (it should not overlap its neighbours). */
  radius: number
}

export interface LayoutLink {
  source: string
  target: string
  weight: number
}

export type Positions = Record<string, { x: number; y: number }>

interface Body extends SimulationNodeDatum {
  id: string
  topic: number | null
  radius: number
}

const TICKS = 300
const REPORT_EVERY = 30
const TOPIC_PULL = 0.07
const TOPIC_SPACING = 240

/** A seeded random source, so the same graph always lands in the same place. */
function seeded(seed = 7): () => number {
  let state = seed
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296
    return state / 4294967296
  }
}

/** Where each topic gathers: on a ring around the centre, wider the more topics there are. */
export function topicAnchors(topics: number[]): Map<number, { x: number; y: number }> {
  const anchors = new Map<number, { x: number; y: number }>()
  const ids = [...new Set(topics)].sort((a, b) => a - b)
  const radius = ids.length <= 1 ? 0 : (TOPIC_SPACING * ids.length) / (2 * Math.PI)
  ids.forEach((id, index) => {
    const angle = (2 * Math.PI * index) / Math.max(ids.length, 1)
    anchors.set(id, { x: radius * Math.cos(angle), y: radius * Math.sin(angle) })
  })
  return anchors
}

/**
 * Places the documents with a force layout: linked ones attract (the stronger the link, the
 * closer), all repel, and the documents of a topic gather around the topic's own spot so the
 * topics read as groups. Deterministic. `onProgress` gets the positions every few steps so the
 * screen can show the graph settling; the last call is the final layout.
 */
export function layoutGraph(
  nodes: LayoutNode[],
  links: LayoutLink[],
  onProgress?: (positions: Positions) => void,
  ticks = TICKS,
): Positions {
  const bodies: Body[] = nodes.map((n) => ({ id: n.id, topic: n.topic, radius: n.radius }))
  const known = new Set(bodies.map((b) => b.id))
  const edges: SimulationLinkDatum<Body>[] = links
    .filter((l) => known.has(l.source) && known.has(l.target))
    .map((l) => ({ source: l.source, target: l.target, weight: l.weight }) as never)
  const anchors = topicAnchors(nodes.flatMap((n) => (n.topic === null ? [] : [n.topic])))
  const anchor = (body: Body) => (body.topic === null ? undefined : anchors.get(body.topic))

  const simulation = forceSimulation(bodies)
    .randomSource(seeded())
    .force(
      'link',
      forceLink<Body, SimulationLinkDatum<Body>>(edges)
        .id((body) => body.id)
        .distance((link) => 130 - 70 * ((link as unknown as LayoutLink).weight ?? 0.5))
        .strength((link) => 0.15 + 0.5 * ((link as unknown as LayoutLink).weight ?? 0.5)),
    )
    .force('charge', forceManyBody<Body>().strength(-140).theta(0.9).distanceMax(700))
    .force(
      'collide',
      forceCollide<Body>((body) => body.radius + 6),
    )
    .force('x', forceX<Body>((body) => anchor(body)?.x ?? 0).strength(TOPIC_PULL))
    .force('y', forceY<Body>((body) => anchor(body)?.y ?? 0).strength(TOPIC_PULL))
    .stop()

  const snapshot = (): Positions =>
    Object.fromEntries(bodies.map((b) => [b.id, { x: b.x ?? 0, y: b.y ?? 0 }]))
  for (let step = 1; step <= ticks && simulation.alpha() > simulation.alphaMin(); step++) {
    simulation.tick()
    if (onProgress && step % REPORT_EVERY === 0) onProgress(snapshot())
  }
  const final = snapshot()
  onProgress?.(final)
  return final
}
