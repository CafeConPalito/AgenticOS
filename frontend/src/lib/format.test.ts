import {
  formatPercent,
  formatSeconds,
  formatTokens,
  formatUsd,
  isoDay,
  shortDay,
  totalTokens,
} from './format'

const nbsp = (text: string) => text.replace(/\u00a0|\u202f/g, ' ')

describe('usage formatters', () => {
  it('abbreviates tokens like the design', () => {
    expect(formatTokens(1_330_000)).toBe('1,33 M')
    expect(formatTokens(230_300)).toBe('230,3 k')
    expect(formatTokens(950)).toBe('950')
  })

  it('formats USD, with «—» when there is no cost', () => {
    expect(nbsp(formatUsd(2.84))).toBe('2,84 $')
    expect(nbsp(formatUsd(0.0042))).toBe('0,0042 $')
    expect(nbsp(formatUsd(0))).toBe('0,00 $')
    expect(formatUsd(null)).toBe('—')
  })

  it('formats percentages and durations', () => {
    expect(nbsp(formatPercent(0.26))).toBe('26 %')
    expect(nbsp(formatPercent(0.12, true))).toBe('+12 %')
    expect(formatSeconds(40)).toBe('40 s')
    expect(formatSeconds(13 * 60)).toBe('13 min')
    expect(formatSeconds(3900)).toBe('1 h 05 min')
    expect(formatSeconds(null)).toBe('—')
  })

  it('counts Claude thinking only once (it is part of the output)', () => {
    const usage = {
      input_tokens: 10,
      output_tokens: 100,
      thinking_tokens: 40,
      cache_read_tokens: 1000,
      cache_creation_tokens: 5,
      cost_usd: null,
    }
    expect(totalTokens(usage, 'claude')).toBe(1115)
    expect(totalTokens(usage, 'agy')).toBe(1155)
  })

  it('works with local days', () => {
    expect(isoDay(new Date(2026, 9, 8, 23, 59))).toBe('2026-10-08')
    expect(shortDay('2026-10-08')).toBe('8 oct')
  })
})
