import type { BranchDecision, Pipeline, Task } from '@/api/types'
import { analyse } from '@/pages/projects/tabs/pipeline/validate'

export type StageState = 'done' | 'current' | 'skipped' | 'pending'

const FINISHED = ['done', 'cancelled']

/**
 * Where a task is in a pipeline with forks (phase 13): the stages already done, the ones it is
 * in now (one per lane), the branches it did not take and what is still ahead.
 */
export function taskPath(
  pipeline: Pipeline,
  task: Task,
  decisions: BranchDecision[] = [],
): Map<string, StageState> {
  const graph = {
    nodes: pipeline.stages.map((s) => ({ key: s.id })),
    edges: pipeline.links.map((l) => ({
      key: l.id,
      source: l.from_stage_id,
      target: l.to_stage_id,
    })),
    rejects: {},
  }
  const { lanes } = analyse(graph)
  const result = new Map<string, StageState>(pipeline.stages.map((s) => [s.id, 'pending']))

  // Where it is now: its own stage, or the stage of each lane that is still going.
  const current = new Set<string>()
  const live = task.lanes.filter((l) => !FINISHED.includes(l.status) && l.stage_id)
  if (task.phase === 'forked' && live.length) live.forEach((l) => current.add(l.stage_id as string))
  else if (!FINISHED.includes(task.status) && task.stage_id) current.add(task.stage_id)

  // Everything before a current stage is done.
  const before = (key: string, seen: Set<string>) => {
    for (const link of pipeline.links)
      if (link.to_stage_id === key && !seen.has(link.from_stage_id)) {
        seen.add(link.from_stage_id)
        before(link.from_stage_id, seen)
      }
  }
  const done = new Set<string>()
  current.forEach((key) => before(key, done))
  if (task.status === 'done') pipeline.stages.forEach((s) => done.add(s.id))
  // The fork a task waits at counts as done once its lanes are going.
  if (task.phase === 'forked' && task.stage_id) done.add(task.stage_id)
  // A lane that arrived is done even when the task is not past the join yet.
  task.lanes.filter((l) => l.status === 'done' && l.stage_id).forEach((l) => done.add(l.stage_id!))

  // The branches of a fork that were decided and not taken.
  const skipped = new Set<string>()
  const taken = new Set([
    ...task.lanes.map((l) => l.link_id).filter((id): id is string => Boolean(id)),
    ...decisions.filter((d) => !d.proposed).flatMap((d) => d.chosen),
  ])
  for (const [fork, branches] of lanes) {
    const outs = pipeline.links
      .filter((l) => l.from_stage_id === fork)
      .sort((a, b) => a.position - b.position)
    const decided =
      task.lanes.some((l) => l.fork_stage_id === fork) ||
      decisions.some((d) => d.fork_stage_id === fork && !d.proposed)
    if (!decided) continue
    branches.forEach((stages, i) => {
      if (outs[i] && !taken.has(outs[i].id)) stages.forEach((s) => skipped.add(s))
    })
  }

  for (const stage of pipeline.stages) {
    if (skipped.has(stage.id)) result.set(stage.id, 'skipped')
    else if (current.has(stage.id)) result.set(stage.id, 'current')
    else if (done.has(stage.id)) result.set(stage.id, 'done')
  }
  return result
}

/** Phase 24: decisions happen at forks and at stages with an exit («Terminar aquí»). */
export const hasDecisions = (pipeline: Pipeline): boolean =>
  hasFork(pipeline) || pipeline.stages.some((s) => s.exit_condition !== null)

export const hasFork = (pipeline: Pipeline): boolean => {
  const count = new Map<string, number>()
  for (const l of pipeline.links) count.set(l.from_stage_id, (count.get(l.from_stage_id) ?? 0) + 1)
  return [...count.values()].some((n) => n > 1)
}
