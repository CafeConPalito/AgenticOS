// S3: how long d3-force takes to lay out a knowledge graph, headless (the Worker runs the same code).
// Graph shape: clusters (topics) with dense links inside and a few between them, like the real one.
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force'

function makeGraph(nodes, edges, clusters) {
  let seed = 7
  const rnd = () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296)
  const ns = Array.from({ length: nodes }, (_, i) => ({ id: i, cluster: i % clusters }))
  const links = []
  const seen = new Set()
  while (links.length < edges) {
    const a = Math.floor(rnd() * nodes)
    const sameCluster = rnd() < 0.85
    let b = Math.floor(rnd() * nodes)
    if (sameCluster) b = (Math.floor(rnd() * (nodes / clusters)) * clusters + (a % clusters)) % nodes
    const key = a < b ? `${a}-${b}` : `${b}-${a}`
    if (a === b || seen.has(key)) continue
    seen.add(key)
    links.push({ source: a, target: b, weight: 0.3 + rnd() * 0.7 })
  }
  return { ns, links }
}

function layout(nodes, edges, clusters) {
  const { ns, links } = makeGraph(nodes, edges, clusters)
  const t = performance.now()
  const sim = forceSimulation(ns)
    .force('link', forceLink(links).distance((l) => 120 - 60 * l.weight).strength((l) => 0.2 + 0.6 * l.weight))
    .force('charge', forceManyBody().strength(-120).theta(0.9).distanceMax(600))
    .force('center', forceCenter(0, 0))
    .force('collide', forceCollide(18))
    .stop()
  let ticks = 0
  while (sim.alpha() > sim.alphaMin() && ticks < 600) {
    sim.tick()
    ticks++
  }
  const ms = performance.now() - t
  const xs = ns.map((n) => n.x), ys = ns.map((n) => n.y)
  return { nodes, edges, ticks, ms: Math.round(ms), w: Math.round(Math.max(...xs) - Math.min(...xs)), h: Math.round(Math.max(...ys) - Math.min(...ys)) }
}

for (const [n, e, c] of [[50, 120, 6], [300, 1000, 12], [600, 2000, 20], [1000, 3500, 30]]) {
  console.log(JSON.stringify(layout(n, e, c)))
}
