/**
 * The shape rules of a pipeline, as the editor checks them while the person draws (phase 13).
 * A port of `backend/src/agentic_os/services/pipeline_graph.py`: the server is the one that
 * decides when saving, so keep both in step (the tests share their cases).
 *
 * A pipeline is a *structured* graph: a stage with several links is a fork, its links are its
 * branches, and all the branches meet again in one stage (the join) or all end in final stages.
 * Forks nest inside a branch. Rejection arrows are not links: they go back to an earlier stage
 * of the same path.
 */

export type GraphErrorCode =
  | 'no_start'
  | 'many_starts'
  | 'unreachable'
  | 'cycle'
  | 'unstructured'
  | 'empty_branch'
  | 'branch_without_condition'
  | 'reject_not_backwards'
  | 'reject_outside_path'

export interface GraphIssueKeys {
  code: GraphErrorCode
  /** Key of the stage the problem is on. */
  stage?: string
  /** Key of the link the problem is on. */
  link?: string
}

export interface GraphNode {
  key: string
}

export interface GraphEdge {
  key: string
  source: string
  target: string
  /** Has a condition, or is «always»: required in the branches of a fork. */
  labelled: boolean
}

/** The stages (in editor order), the links, and where each stage can send tasks back to. */
export interface GraphInput {
  nodes: GraphNode[]
  edges: GraphEdge[]
  rejects: Record<string, string[]>
}

/** A position inside the forks: [fork, branch index] pairs from the outermost one. */
type Path = [string, number][]

export interface Structure {
  issues: GraphIssueKeys[]
  /** Stage → its position inside the forks (only filled when the structure is sound). */
  paths: Map<string, Path>
  /** Fork → the stage where its branches meet (null: they never meet). */
  joins: Map<string, string | null>
  /** Fork → the stages of each of its branches. */
  lanes: Map<string, string[][]>
}

export function analyse(graph: GraphInput): Structure {
  const keys = graph.nodes.map((n) => n.key)
  const out = new Map<string, GraphEdge[]>(keys.map((k) => [k, []]))
  const inc = new Map<string, GraphEdge[]>(keys.map((k) => [k, []]))
  for (const edge of graph.edges) {
    out.get(edge.source)?.push(edge)
    inc.get(edge.target)?.push(edge)
  }
  const issues: GraphIssueKeys[] = []
  const starts = keys.filter((k) => !inc.get(k)?.length)
  if (!starts.length) issues.push({ code: 'no_start' })
  for (const key of starts.slice(1)) issues.push({ code: 'many_starts', stage: key })

  // Topological order (Kahn); what is left over is in a cycle.
  const degree = new Map(keys.map((k) => [k, inc.get(k)?.length ?? 0]))
  const ready = keys.filter((k) => degree.get(k) === 0)
  const order: string[] = []
  while (ready.length) {
    const key = ready.shift() as string
    order.push(key)
    for (const edge of out.get(key) ?? []) {
      degree.set(edge.target, (degree.get(edge.target) ?? 1) - 1)
      if (degree.get(edge.target) === 0) ready.push(edge.target)
    }
  }
  const cyclic = keys.filter((k) => !order.includes(k))
  for (const key of cyclic) issues.push({ code: 'cycle', stage: key })

  for (const key of keys) {
    const outs = out.get(key) ?? []
    if (outs.length > 1)
      for (const edge of outs)
        if (!edge.labelled)
          issues.push({ code: 'branch_without_condition', stage: key, link: edge.key })
  }

  const forward = new Map<string, Set<string>>()
  const reach = (key: string): Set<string> => {
    const cached = forward.get(key)
    if (cached) return cached
    forward.set(key, new Set()) // guards against cycles
    const found = new Set<string>()
    for (const edge of out.get(key) ?? []) {
      found.add(edge.target)
      for (const next of reach(edge.target)) found.add(next)
    }
    forward.set(key, found)
    return found
  }

  const paths = new Map<string, Path>()
  const joins = new Map<string, string | null>()
  const lanes = new Map<string, string[][]>()
  let structured = false
  if (!cyclic.length && starts.length === 1) {
    const before = issues.length
    const joinOf = (fork: string): string | null => {
      const sets = (out.get(fork) ?? []).map((e) => new Set([e.target, ...reach(e.target)]))
      const common = [...sets[0]].filter((k) => sets.every((s) => s.has(k)))
      return order.find((k) => common.includes(k)) ?? null
    }
    const walk = (start: string | null, path: Path, stop: string | null) => {
      let node = start
      while (node !== null && node !== stop) {
        if (paths.has(node)) {
          issues.push({ code: 'unstructured', stage: node })
          return
        }
        paths.set(node, path)
        const outs = out.get(node) ?? []
        if (!outs.length) return
        if (outs.length === 1) {
          node = outs[0].target
          continue
        }
        const join = joinOf(node)
        joins.set(node, join)
        if (join !== null && join === stop) {
          issues.push({ code: 'unstructured', stage: node })
          return
        }
        const found: string[][] = []
        outs.forEach((edge, index) => {
          if (edge.target === join) {
            issues.push({ code: 'empty_branch', stage: node as string, link: edge.key })
            found.push([])
            return
          }
          const known = new Set(paths.keys())
          walk(edge.target, [...path, [node as string, index]], join)
          found.push([...paths.keys()].filter((k) => !known.has(k)))
        })
        lanes.set(node, found)
        node = join
      }
    }
    walk(starts[0], [], null)
    structured = issues.length === before
  }

  for (const [stage, targets] of Object.entries(graph.rejects)) {
    for (const target of targets) {
      if (stage === target || !reach(target).has(stage)) {
        issues.push({ code: 'reject_not_backwards', stage })
      } else if (structured) {
        const mine = paths.get(stage) ?? []
        const theirs = paths.get(target) ?? []
        // Inside a branch a stage only sends tasks back within that branch.
        const inside = mine.every(
          (step, i) => theirs[i]?.[0] === step[0] && theirs[i][1] === step[1],
        )
        if (!inside) issues.push({ code: 'reject_outside_path', stage })
      }
    }
  }
  return { issues, paths, joins, lanes }
}

export function validateGraph(graph: GraphInput): GraphIssueKeys[] {
  return analyse(graph).issues
}

/** The stages a stage can send tasks back to, in the same path as the stage. */
export function rejectCandidates(graph: GraphInput, stage: string): string[] {
  const { paths } = analyse({ ...graph, rejects: {} })
  const mine = paths.get(stage)
  if (!mine) return []
  const seen = new Set<string>()
  const back = (key: string) => {
    for (const edge of graph.edges)
      if (edge.target === key && !seen.has(edge.source)) {
        seen.add(edge.source)
        back(edge.source)
      }
  }
  back(stage)
  return graph.nodes
    .map((n) => n.key)
    .filter((key) => {
      const theirs = paths.get(key)
      return (
        seen.has(key) &&
        theirs !== undefined &&
        mine.every((step, i) => theirs[i]?.[0] === step[0] && theirs[i][1] === step[1])
      )
    })
}
