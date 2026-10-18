import type { DeciderCli, LinkWrite, Pipeline, PipelineWrite, Stage, StageWrite } from '@/api/types'
import type { GraphInput } from './validate'

/** A stage being edited. `key` is stable while editing; links and rejections point at keys. */
export interface DraftStage {
  key: string
  id: string | null
  name: string
  agentId: string | null
  requiresReview: boolean
  /** Default stage a rejection goes back to. */
  rejectTo: string | null
  /** Other stages it can also send tasks back to. */
  rejectAlso: string[]
  confirmDecision: boolean
  x: number
  y: number
  activeTasks: number
}

/** A link between two stages; with several leaving a stage, each is a branch. */
export interface DraftLink {
  key: string
  id: string | null
  source: string
  target: string
  name: string
  condition: string
  always: boolean
}

export interface Draft {
  name: string
  maxRejections: number
  deciderCli: DeciderCli | null
  deciderAccountId: string | null
  deciderModel: string
  stages: DraftStage[]
  links: DraftLink[]
}

let seq = 0
export const newKey = (prefix = 'new') => `${prefix}-${++seq}`

export function newStage(name: string, x: number, y: number): DraftStage {
  return {
    key: newKey('stage'),
    id: null,
    name,
    agentId: null,
    requiresReview: false,
    rejectTo: null,
    rejectAlso: [],
    confirmDecision: false,
    x,
    y,
    activeTasks: 0,
  }
}

export function newLink(source: string, target: string, name = ''): DraftLink {
  return {
    key: newKey('link'),
    id: null,
    source,
    target,
    name,
    condition: '',
    always: false,
  }
}

export function emptyDraft(firstStage: string): Draft {
  return {
    name: '',
    maxRejections: 3,
    deciderCli: null,
    deciderAccountId: null,
    deciderModel: '',
    stages: [newStage(firstStage, 0, 0)],
    links: [],
  }
}

export function toDraft(pipeline: Pipeline): Draft {
  return {
    name: pipeline.name,
    maxRejections: pipeline.max_rejections,
    deciderCli: pipeline.decider_cli,
    deciderAccountId: pipeline.decider_account_id,
    deciderModel: pipeline.decider_model ?? '',
    stages: pipeline.stages.map((s: Stage) => ({
      key: s.id,
      id: s.id,
      name: s.name,
      agentId: s.agent_id,
      requiresReview: s.requires_review,
      rejectTo: s.reject_to_stage_id,
      rejectAlso: s.reject_extra_stage_ids,
      confirmDecision: s.confirm_decision,
      x: s.x,
      y: s.y,
      activeTasks: s.active_tasks,
    })),
    links: [...pipeline.links]
      .sort((a, b) => a.position - b.position)
      .map((l) => ({
        key: l.id,
        id: l.id,
        source: l.from_stage_id,
        target: l.to_stage_id,
        name: l.name,
        condition: l.condition,
        always: l.always,
      })),
  }
}

/** What the server saves: stages in editor order, links and rejections by index. */
export function toWrite(draft: Draft): PipelineWrite {
  const index = new Map(draft.stages.map((s, i) => [s.key, i]))
  const at = (key: string | null) => (key === null ? null : (index.get(key) ?? null))
  const stages: StageWrite[] = draft.stages.map((s) => ({
    id: s.id,
    name: s.name.trim(),
    agent_id: s.agentId,
    requires_review: s.requiresReview,
    reject_to: at(s.rejectTo),
    reject_also: s.rejectAlso.map((k) => index.get(k)).filter((i): i is number => i !== undefined),
    x: Math.round(s.x),
    y: Math.round(s.y),
    confirm_decision: s.confirmDecision,
  }))
  const links: LinkWrite[] = draft.links.map((l) => ({
    source: index.get(l.source) ?? 0,
    target: index.get(l.target) ?? 0,
    name: l.name.trim(),
    condition: l.condition.trim(),
    always: l.always,
  }))
  return {
    name: draft.name,
    max_rejections: draft.maxRejections,
    stages,
    links,
    decider_cli: draft.deciderCli,
    decider_account_id: draft.deciderAccountId,
    decider_model: draft.deciderModel.trim() || null,
  }
}

export function graphOf(draft: Draft): GraphInput {
  const rejects: Record<string, string[]> = {}
  for (const s of draft.stages) {
    const targets = [s.rejectTo, ...s.rejectAlso].filter((k): k is string => Boolean(k))
    if (targets.length) rejects[s.key] = targets
  }
  return {
    nodes: draft.stages.map((s) => ({ key: s.key })),
    edges: draft.links.map((l) => ({
      key: l.key,
      source: l.source,
      target: l.target,
      labelled: l.always || Boolean(l.condition.trim()),
    })),
    rejects,
  }
}

/** The links that leave a stage, in order. */
export function linksFrom(draft: Draft, key: string): DraftLink[] {
  return draft.links.filter((l) => l.source === key)
}

/** Columns by depth, rows in editor order: a readable place for every stage. */
export function autoLayout(draft: Draft): Draft {
  const depth = new Map<string, number>()
  const place = (key: string, seen: Set<string>): number => {
    const known = depth.get(key)
    if (known !== undefined) return known
    if (seen.has(key)) return 0
    seen.add(key)
    const parents = draft.links.filter((l) => l.target === key).map((l) => l.source)
    const value = parents.length ? Math.max(...parents.map((p) => place(p, seen))) + 1 : 0
    depth.set(key, value)
    return value
  }
  const rows = new Map<number, number>()
  const stages = draft.stages.map((s) => {
    const column = place(s.key, new Set())
    const row = rows.get(column) ?? 0
    rows.set(column, row + 1)
    return { ...s, x: column * 300, y: row * 170 }
  })
  return { ...draft, stages }
}

/** Removes a stage and everything that pointed at it; the links around it are dropped. */
export function withoutStage(draft: Draft, key: string): Draft {
  return {
    ...draft,
    stages: draft.stages
      .filter((s) => s.key !== key)
      .map((s) => ({
        ...s,
        rejectTo: s.rejectTo === key ? null : s.rejectTo,
        rejectAlso: s.rejectAlso.filter((k) => k !== key),
      })),
    links: draft.links.filter((l) => l.source !== key && l.target !== key),
  }
}

/** A rejection with no target keeps no extra ones. */
export function tidy(draft: Draft): Draft {
  return {
    ...draft,
    stages: draft.stages.map((s) =>
      s.rejectTo || !s.rejectAlso.length
        ? s
        : { ...s, rejectTo: s.rejectAlso[0], rejectAlso: s.rejectAlso.slice(1) },
    ),
  }
}
