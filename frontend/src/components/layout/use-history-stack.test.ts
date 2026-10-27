import { NavigationType } from 'react-router'
import { step } from './use-history-stack'

const { Push, Pop, Replace } = NavigationType

describe('history stack', () => {
  const start = { keys: ['a'], pos: 0 }

  it('pushes, goes back and forward, and drops what was ahead on a new push', () => {
    let s = step(start, Push, 'b')
    s = step(s, Push, 'c')
    expect(s).toEqual({ keys: ['a', 'b', 'c'], pos: 2 })
    s = step(s, Pop, 'a')
    expect(s.pos).toBe(0)
    s = step(s, Pop, 'b')
    expect(s.pos).toBe(1)
    s = step(s, Push, 'd')
    expect(s).toEqual({ keys: ['a', 'b', 'd'], pos: 2 })
  })

  it('replaces in place and ignores the same key twice (Strict Mode effects)', () => {
    const s = step(step(start, Push, 'b'), Replace, 'b2')
    expect(s).toEqual({ keys: ['a', 'b2'], pos: 1 })
    expect(step(s, Push, 'b2')).toBe(s)
  })

  it('starts again from an entry it never saw', () => {
    expect(step(start, Pop, 'zzz')).toEqual({ keys: ['zzz'], pos: 0 })
  })
})
