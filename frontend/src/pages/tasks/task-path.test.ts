import type { Lane, Pipeline, PipelineLink, Task } from '@/api/types'
import { makePipeline, makeTask } from '@/test/fake-backend'
import { hasFork, taskPath } from './task-path'

// Requisitos → (Backend | Frontend | Docs) → QA
function split(): Pipeline {
  const pipeline = makePipeline(
    'p',
    [
      { id: 'req', name: 'Requisitos' },
      { id: 'back', name: 'Backend' },
      { id: 'front', name: 'Frontend' },
      { id: 'docs', name: 'Docs' },
      { id: 'qa', name: 'QA' },
    ],
    { links: [] },
  )
  const link = (id: string, from: string, to: string, position: number): PipelineLink => ({
    id,
    from_stage_id: from,
    to_stage_id: to,
    name: id,
    condition: 'x',
    always: false,
    position,
  })
  pipeline.links = [
    link('l-back', 'req', 'back', 0),
    link('l-front', 'req', 'front', 1),
    link('l-docs', 'req', 'docs', 2),
    link('b-qa', 'back', 'qa', 0),
    link('f-qa', 'front', 'qa', 0),
    link('d-qa', 'docs', 'qa', 0),
  ]
  return pipeline
}

const lane = (overrides: Partial<Lane>): Lane => ({
  id: 'lane',
  code: 'T-1·x',
  lane_key: 'x',
  name: 'x',
  status: 'running',
  stage_id: null,
  stage_name: null,
  agent_name: null,
  agent_color: null,
  waiting_reason: null,
  link_id: null,
  fork_stage_id: 'req',
  ...overrides,
})

const task = (overrides: Partial<Task>): Task => makeTask(overrides)

describe('the path of a task through a pipeline with forks', () => {
  it('knows which pipelines fork', () => {
    expect(hasFork(split())).toBe(true)
    expect(hasFork(makePipeline('p', [{ name: 'A' }, { name: 'B' }]))).toBe(false)
  })

  it('before the fork only the current stage is marked', () => {
    const path = taskPath(split(), task({ stage_id: 'req', status: 'running' }))
    expect(path.get('req')).toBe('current')
    expect(['back', 'front', 'docs', 'qa'].map((k) => path.get(k))).toEqual([
      'pending',
      'pending',
      'pending',
      'pending',
    ])
  })

  it('with the lanes going: the fork is done, each lane is where it is, the branch not taken is skipped', () => {
    const lanes = [
      lane({ link_id: 'l-back', stage_id: 'back', status: 'running' }),
      lane({ link_id: 'l-front', stage_id: 'front', status: 'done' }),
    ]
    const path = taskPath(split(), task({ stage_id: 'req', phase: 'forked', lanes }))
    expect(path.get('req')).toBe('done')
    expect(path.get('back')).toBe('current')
    expect(path.get('front')).toBe('done') // that lane arrived
    expect(path.get('docs')).toBe('skipped')
    expect(path.get('qa')).toBe('pending')
  })

  it('after the join the task is at the join and the branches behind it are done', () => {
    const lanes = [
      lane({ link_id: 'l-back', stage_id: 'back', status: 'done' }),
      lane({ link_id: 'l-front', stage_id: 'front', status: 'done' }),
    ]
    const path = taskPath(split(), task({ stage_id: 'qa', lanes }))
    expect(path.get('qa')).toBe('current')
    expect(path.get('req')).toBe('done')
    expect(path.get('back')).toBe('done')
    expect(path.get('docs')).toBe('skipped')
  })

  it('a finished task has everything done except what it skipped', () => {
    const lanes = [lane({ link_id: 'l-back', stage_id: 'back', status: 'done' })]
    const path = taskPath(split(), task({ stage_id: 'qa', status: 'done', lanes }))
    expect(path.get('qa')).toBe('done')
    expect(path.get('front')).toBe('skipped')
    expect(path.get('docs')).toBe('skipped')
  })

  it('a decision that is only proposed skips nothing yet', () => {
    const path = taskPath(split(), task({ stage_id: 'req', status: 'review' }), [
      {
        id: 'd',
        at: '',
        fork_stage_id: 'req',
        decided_by: 'model',
        proposed: true,
        chosen: ['l-back'],
        reasons: {},
        error: null,
        run_id: null,
      },
    ])
    expect(path.get('front')).toBe('pending')
  })
})
