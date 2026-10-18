/** The lanes of a commit graph, computed from the order of the history and each commit's parents
 * (phase 12). It needs nothing else, so a new page of the history continues from the lanes the
 * last one left. */

export interface GraphCommit {
  sha: string
  parents: string[]
}

export interface GraphRow {
  /** Column of this commit's dot. */
  lane: number
  /** Something above was waiting for this commit (a branch tip has nothing above it). */
  fromAbove: boolean
  /** Columns whose line comes down from the row above into the dot (merges into this commit). */
  incoming: number[]
  /** Columns of the lines going down from the dot: one per parent. */
  outgoing: number[]
  /** Columns whose line just passes through this row, untouched. */
  through: number[]
  /** Width of the row, in columns. */
  width: number
}

/** The lanes still open after the last row: what each one waits for. */
export type Lanes = (string | null)[]

function free(lanes: Lanes, avoid: number): number {
  const index = lanes.findIndex((sha, i) => sha === null && i !== avoid)
  if (index >= 0) return index
  lanes.push(null)
  return lanes.length - 1
}

export function layoutGraph(
  commits: GraphCommit[],
  carried: Lanes = [],
): { rows: GraphRow[]; lanes: Lanes } {
  const lanes: Lanes = [...carried]
  const rows: GraphRow[] = []
  for (const commit of commits) {
    const waiting = lanes.flatMap((sha, i) => (sha === commit.sha ? [i] : []))
    let lane = waiting[0] ?? -1
    if (lane < 0) {
      lane = lanes.indexOf(null)
      if (lane < 0) {
        lanes.push(null)
        lane = lanes.length - 1
      }
    }
    const through = lanes.flatMap((sha, i) =>
      sha !== null && sha !== commit.sha && i !== lane ? [i] : [],
    )
    for (const i of waiting) lanes[i] = null

    const outgoing: number[] = []
    commit.parents.forEach((parent, position) => {
      const existing = lanes.indexOf(parent)
      if (existing >= 0) {
        outgoing.push(existing) // another branch already waits for it: join that line
        return
      }
      const target = position === 0 && lanes[lane] === null ? lane : free(lanes, lane)
      lanes[target] = parent
      outgoing.push(target)
    })
    while (lanes.length > 0 && lanes[lanes.length - 1] === null) lanes.pop()

    const used = [lane, ...waiting, ...outgoing, ...through]
    rows.push({
      lane,
      fromAbove: waiting.length > 0,
      incoming: waiting.filter((i) => i !== lane),
      outgoing,
      through,
      width: Math.max(...used) + 1,
    })
  }
  return { rows, lanes }
}

/** The widest row, in columns (all rows share one width so the text lines up). */
export function graphWidth(rows: GraphRow[]): number {
  return rows.reduce((width, row) => Math.max(width, row.width), 1)
}
