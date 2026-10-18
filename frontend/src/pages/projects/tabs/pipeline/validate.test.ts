import { analyse, rejectCandidates, validateGraph, type GraphInput } from './validate'

// The same graphs as backend/tests/test_pipeline_graph.py: the editor and the server must agree.
function graph(
  links: [string, string][],
  rejects: Record<string, string[]> = {},
  nodes?: string,
  unlabelled: string[] = [],
): GraphInput {
  const names = nodes ? [...nodes] : [...new Set(links.flat())].sort()
  return {
    nodes: names.map((key) => ({ key })),
    edges: links.map(([source, target]) => ({
      key: `${source}${target}`,
      source,
      target,
      labelled: !unlabelled.includes(`${source}${target}`),
    })),
    rejects,
  }
}

const codes = (g: GraphInput) => validateGraph(g).map((i) => i.code)

const LINEAR: [string, string][] = [
  ['A', 'B'],
  ['B', 'C'],
]
const DIAMOND: [string, string][] = [
  ['A', 'B'],
  ['A', 'C'],
  ['B', 'D'],
  ['C', 'D'],
]
const LONG: [string, string][] = [
  ['A', 'B'],
  ['B', 'B2'],
  ['A', 'C'],
  ['B2', 'D'],
  ['C', 'D'],
  ['D', 'E'],
]

describe('pipeline graph rules', () => {
  it('accepts a chain', () => {
    expect(validateGraph(graph(LINEAR))).toEqual([])
  })

  it('finds the join and the lanes of a fork', () => {
    const result = analyse(graph(DIAMOND, { D: ['B'] }))
    expect(result.issues).toEqual([])
    expect(result.joins.get('A')).toBe('D')
    expect(result.lanes.get('A')).toEqual([['B'], ['C']])
    expect(result.paths.get('B')).toEqual([['A', 0]])
    expect(result.paths.get('D')).toEqual([])
  })

  it('lets a lane have several stages and forks nest inside a branch', () => {
    expect(analyse(graph(LONG)).lanes.get('A')?.[0]).toEqual(['B', 'B2'])
    const nested = graph([
      ['A', 'B'],
      ['A', 'C'],
      ['B', 'X'],
      ['B', 'Y'],
      ['X', 'Z'],
      ['Y', 'Z'],
      ['Z', 'D'],
      ['C', 'D'],
    ])
    const result = analyse(nested)
    expect(result.issues).toEqual([])
    expect(result.joins.get('A')).toBe('D')
    expect(result.joins.get('B')).toBe('Z')
    expect(result.lanes.get('A')?.[0]).toEqual(['B', 'X', 'Y', 'Z'])
  })

  it('accepts branches that never meet', () => {
    const result = analyse(
      graph([
        ['A', 'B'],
        ['A', 'C'],
      ]),
    )
    expect(result.issues).toEqual([])
    expect(result.joins.get('A')).toBeNull()
  })

  it('needs exactly one start and no cycles', () => {
    expect(
      codes(
        graph([
          ['A', 'C'],
          ['B', 'C'],
        ]),
      ),
    ).toContain('many_starts')
    expect(codes(graph([], {}, ''))).toContain('no_start')
    expect(
      codes(
        graph([
          ['A', 'B'],
          ['B', 'C'],
          ['C', 'B'],
        ]),
      ),
    ).toContain('cycle')
    const lonely = codes(
      graph([
        ['A', 'B'],
        ['B', 'A'],
      ]),
    )
    expect(lonely).toContain('no_start')
    expect(lonely).toContain('cycle')
  })

  it('wants a condition or «always» on every branch of a fork', () => {
    const issues = validateGraph(graph(DIAMOND, {}, undefined, ['AC']))
    expect(issues).toEqual([{ code: 'branch_without_condition', stage: 'A', link: 'AC' }])
    // a single link has nothing to decide
    expect(validateGraph(graph([['A', 'B']], {}, undefined, ['AB']))).toEqual([])
  })

  it('refuses crossing lanes, empty branches and forks closing on the outer join', () => {
    expect(
      codes(
        graph([
          ['A', 'B'],
          ['A', 'C'],
          ['B', 'D'],
          ['B', 'C'],
          ['C', 'D'],
        ]),
      ),
    ).toContain('unstructured')
    expect(
      codes(
        graph([
          ['A', 'B'],
          ['A', 'C'],
          ['B', 'C'],
        ]),
      ),
    ).toContain('empty_branch')
    const nested = graph([
      ['A', 'B'],
      ['A', 'C'],
      ['B', 'X'],
      ['B', 'Y'],
      ['X', 'D'],
      ['Y', 'D'],
      ['C', 'D'],
    ])
    expect(codes(nested)).toContain('unstructured')
  })

  it('sends a rejection back to an earlier stage of the path', () => {
    expect(validateGraph(graph(LINEAR, { C: ['A'] }))).toEqual([])
    expect(codes(graph(LINEAR, { A: ['C'] }))).toEqual(['reject_not_backwards'])
    expect(codes(graph(LINEAR, { B: ['B'] }))).toEqual(['reject_not_backwards'])
  })

  it('after a join a stage may reject to any branch or before the fork', () => {
    for (const target of ['A', 'B', 'C'])
      expect(validateGraph(graph(DIAMOND, { D: [target] }))).toEqual([])
    expect(validateGraph(graph([...LONG, ['E', 'F']], { F: ['B'] }))).toEqual([])
  })

  it('inside a branch a stage only rejects within that branch', () => {
    expect(validateGraph(graph(LONG, { B2: ['B'] }))).toEqual([])
    expect(codes(graph(LONG, { B2: ['A'] }))).toEqual(['reject_outside_path'])
    expect(codes(graph(LONG, { B2: ['C'] }))).toEqual(['reject_not_backwards'])
  })

  it('offers as rejection targets the earlier stages of the path', () => {
    expect(rejectCandidates(graph(DIAMOND), 'D').sort()).toEqual(['A', 'B', 'C'])
    expect(rejectCandidates(graph(LONG), 'B2').sort()).toEqual(['B'])
    expect(rejectCandidates(graph(LINEAR), 'A')).toEqual([])
  })
})
