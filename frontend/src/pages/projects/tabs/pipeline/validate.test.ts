import { makePipeline } from '@/test/fake-backend'
import { graphOf, toDraft, toWrite } from './model'
import { analyse, rejectCandidates, validateGraph, type GraphInput } from './validate'

// The same graphs as backend/tests/test_pipeline_graph.py: the editor and the server must agree.
function graph(
  links: [string, string][],
  rejects: Record<string, string[]> = {},
  nodes?: string,
): GraphInput {
  const names = nodes ? [...nodes] : [...new Set(links.flat())].sort()
  return {
    nodes: names.map((key) => ({ key })),
    edges: links.map(([source, target]) => ({
      key: `${source}${target}`,
      source,
      target,
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

  it('takes a branch without a condition as always taken (phase 21)', () => {
    expect(validateGraph(graph(DIAMOND))).toEqual([])
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

// Phase 24 (ADR 0030): the same cases as backend/tests/test_pipeline_exits_graph.py.
describe('«Terminar aquí» exits', () => {
  // A → (B | C) → D → E
  const WITH_TAIL: [string, string][] = [...DIAMOND, ['D', 'E']]
  const exits = (links: [string, string][], at: Record<string, string>) => ({
    ...graph(links),
    exits: at,
  })
  const found = (g: GraphInput) => validateGraph(g).map((i) => [i.code, i.stage])

  it('is valid before the fork, on the fork and after the join', () => {
    expect(validateGraph(exits(WITH_TAIL, { A: 'Solo requisitos', D: 'Sin despliegue' }))).toEqual(
      [],
    )
  })

  it('needs a condition', () => {
    expect(found(exits(WITH_TAIL, { A: '   ' }))).toEqual([['exit_no_condition', 'A']])
  })

  it('is not needed on a final stage', () => {
    expect(found(exits(WITH_TAIL, { E: 'Terminar' }))).toEqual([['exit_on_final', 'E']])
  })

  it('cannot sit inside an open fork', () => {
    expect(found(exits(WITH_TAIL, { B: 'Terminar', C: 'Terminar' }))).toEqual([
      ['exit_in_branch', 'B'],
      ['exit_in_branch', 'C'],
    ])
    const apart: [string, string][] = [
      ['A', 'B'],
      ['B', 'B2'],
      ['A', 'C'],
    ]
    expect(found(exits(apart, { B: 'Terminar' }))).toEqual([['exit_in_branch', 'B']])
    expect(found(exits(apart, { C: 'Terminar' }))).toEqual([['exit_on_final', 'C']])
  })
})

describe('the editor model keeps the exits (phase 24)', () => {
  it('reads an exit, writes it back trimmed and drops it when removed', () => {
    const pipeline = makePipeline('p1', [
      { id: 's1', name: 'Requisitos' },
      { id: 's2', name: 'Validación', exit_condition: 'Solo requisitos', exit_x: 300, exit_y: 120 },
      { id: 's3', name: 'Desarrollo' },
    ])
    const draft = toDraft(pipeline)
    expect(draft.stages[1].exit).toEqual({ condition: 'Solo requisitos', x: 300, y: 120 })
    expect(draft.stages[0].exit).toBeNull()
    expect(graphOf(draft).exits).toEqual({ s2: 'Solo requisitos' })

    draft.stages[1].exit = { condition: '  Solo requisitos  ', x: 310.4, y: 99.6 }
    const written = toWrite(draft).stages
    expect(written[1]).toMatchObject({
      exit_condition: 'Solo requisitos',
      exit_x: 310,
      exit_y: 100,
    })
    expect(written[0]).toMatchObject({ exit_condition: null, exit_x: null, exit_y: null })

    draft.stages[1].exit = null
    expect(toWrite(draft).stages[1].exit_condition).toBeNull()
  })

  it('places the «Fin» node under its stage when the server has no place for it', () => {
    const pipeline = makePipeline('p1', [
      { id: 's1', name: 'A', x: 40, y: 10, exit_condition: 'Terminar', exit_x: null, exit_y: null },
      { id: 's2', name: 'B' },
    ])
    expect(toDraft(pipeline).stages[0].exit).toEqual({ condition: 'Terminar', x: 40, y: 120 })
  })
})
