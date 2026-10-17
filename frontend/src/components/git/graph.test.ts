import { layoutGraph, graphWidth, type GraphCommit } from './graph'

const c = (sha: string, ...parents: string[]): GraphCommit => ({ sha, parents })

describe('layoutGraph', () => {
  it('keeps a straight history in one lane', () => {
    const { rows, lanes } = layoutGraph([c('a', 'b'), c('b', 'c'), c('c')])
    expect(rows.map((r) => r.lane)).toEqual([0, 0, 0])
    expect(rows.map((r) => r.outgoing)).toEqual([[0], [0], []])
    expect(rows.every((r) => r.through.length === 0 && r.incoming.length === 0)).toBe(true)
    expect(lanes).toEqual([])
  })

  it('opens a lane for the second parent of a merge and joins it back', () => {
    // m merges a (first parent) and b; both come from r.
    const { rows } = layoutGraph([c('m', 'a', 'b'), c('a', 'r'), c('b', 'r'), c('r')])
    expect(rows[0]).toMatchObject({ lane: 0, outgoing: [0, 1] })
    expect(rows[1]).toMatchObject({ lane: 0, through: [1], outgoing: [0] })
    // b sits on its own lane and its line bends into the lane r waits in.
    expect(rows[2]).toMatchObject({ lane: 1, through: [0], outgoing: [0] })
    expect(rows[3]).toMatchObject({ lane: 0, incoming: [], outgoing: [] })
    expect(graphWidth(rows)).toBe(2)
  })

  it('draws the lines of several branches that end in the same commit', () => {
    // Two tips (x, y) with the same parent p, listed one after the other.
    const { rows } = layoutGraph([c('x', 'p'), c('y', 'p'), c('p')])
    expect(rows[0]).toMatchObject({ lane: 0, outgoing: [0] })
    expect(rows[1]).toMatchObject({ lane: 1, through: [0], outgoing: [0] })
    expect(rows[2]).toMatchObject({ lane: 0 })
  })

  it('reuses the lane a commit was waited in when two lines meet at it', () => {
    // a and b both have p as their only parent but p is reached through two lanes first.
    const { rows } = layoutGraph([c('a', 'p', 'q'), c('b', 'q'), c('p', 'q'), c('q')])
    const last = rows[3]
    expect(last.lane).toBeGreaterThanOrEqual(0)
    expect(new Set([last.lane, ...last.incoming]).size).toBe(1 + last.incoming.length)
  })

  it('continues from the lanes a page left, as if it were one list', () => {
    const history = [c('m', 'a', 'b'), c('a', 'r'), c('b', 'r'), c('r', 's'), c('s')]
    const whole = layoutGraph(history).rows
    const first = layoutGraph(history.slice(0, 2))
    const second = layoutGraph(history.slice(2), first.lanes)
    expect([...first.rows, ...second.rows]).toEqual(whole)
  })

  it('handles an octopus merge and unrelated roots', () => {
    const { rows } = layoutGraph([c('o', 'a', 'b', 'c'), c('a'), c('b'), c('c'), c('z')])
    expect(rows[0].outgoing).toEqual([0, 1, 2])
    expect(rows.map((r) => r.lane)).toEqual([0, 0, 1, 2, 0])
  })
})
