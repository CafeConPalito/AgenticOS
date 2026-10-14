import { describe, expect, it } from 'vitest'
import { shortcutFor, type ShortcutContext } from './shortcuts'

const ctx: ShortcutContext = { singleKeyShortcuts: true, dialogOpen: false }

function key(init: KeyboardEventInit, target?: Element) {
  const e = new KeyboardEvent('keydown', { bubbles: true, ...init })
  Object.defineProperty(e, 'target', { value: target ?? document.body })
  return e
}

/** Renders `html` and returns its `[data-t]` element (the one that has the focus). */
function el(html: string): Element {
  document.body.innerHTML = html
  return document.body.querySelector('[data-t]')!
}

describe('shortcutFor', () => {
  it('Ctrl+K opens the palette, also from a field', () => {
    expect(shortcutFor(key({ key: 'k', ctrlKey: true }), ctx)).toBe('palette')
    const input = el('<div><input data-t /></div>')
    expect(shortcutFor(key({ key: 'k', ctrlKey: true }, input), ctx)).toBe('palette')
  })

  it('Ctrl+K does nothing inside a terminal (xterm or the dock)', () => {
    const xterm = el('<div class="xterm"><textarea data-t></textarea></div>')
    expect(shortcutFor(key({ key: 'k', ctrlKey: true }, xterm), ctx)).toBeNull()
    const dock = el('<aside data-terminal-dock><button data-t></button></aside>')
    expect(shortcutFor(key({ key: 'k', ctrlKey: true }, dock), ctx)).toBeNull()
  })

  it('N and ? work on the page', () => {
    expect(shortcutFor(key({ key: 'n' }), ctx)).toBe('newTask')
    expect(shortcutFor(key({ key: 'N' }), ctx)).toBe('newTask')
    expect(shortcutFor(key({ key: '?', shiftKey: true }), ctx)).toBe('shortcuts')
  })

  it.each([
    ['input', '<div><input data-t /></div>'],
    ['textarea', '<div><textarea data-t></textarea></div>'],
    ['select', '<div><select data-t></select></div>'],
    ['contenteditable', '<div contenteditable="true" data-t></div>'],
    ['xterm', '<div class="xterm"><textarea data-t></textarea></div>'],
    ['dock', '<aside data-terminal-dock><button data-t></button></aside>'],
  ])('single keys do not act in %s', (_name, html) => {
    const target = el(html)
    expect(shortcutFor(key({ key: 'n' }, target), ctx)).toBeNull()
    expect(shortcutFor(key({ key: '?' }, target), ctx)).toBeNull()
  })

  it('single keys do not act with a dialog open, a modifier or the preference off', () => {
    expect(shortcutFor(key({ key: 'n' }), { ...ctx, dialogOpen: true })).toBeNull()
    expect(shortcutFor(key({ key: 'n', ctrlKey: true }), ctx)).toBeNull()
    expect(shortcutFor(key({ key: 'n', altKey: true }), ctx)).toBeNull()
    expect(shortcutFor(key({ key: 'n', metaKey: true }), ctx)).toBeNull()
    expect(shortcutFor(key({ key: 'n' }), { ...ctx, singleKeyShortcuts: false })).toBeNull()
    expect(shortcutFor(key({ key: '?' }), { ...ctx, singleKeyShortcuts: false })).toBeNull()
  })

  it('single keys do not act with a menu, select list or popover open', () => {
    expect(shortcutFor(key({ key: 'n' }), { ...ctx, menuOpen: true })).toBeNull()
    expect(shortcutFor(key({ key: '?' }), { ...ctx, menuOpen: true })).toBeNull()
  })

  it('Ctrl+K does not stack over another dialog, but can close the palette itself', () => {
    const k = key({ key: 'k', ctrlKey: true })
    expect(shortcutFor(k, { ...ctx, dialogOpen: true })).toBeNull()
    expect(shortcutFor(k, { ...ctx, dialogOpen: true, paletteOpen: true })).toBe('palette')
  })

  it('Ctrl+K still works with the single-key preference off', () => {
    const off = { ...ctx, singleKeyShortcuts: false }
    expect(shortcutFor(key({ key: 'k', ctrlKey: true }), off)).toBe('palette')
  })

  it('ignores other keys', () => {
    expect(shortcutFor(key({ key: 'a' }), ctx)).toBeNull()
    expect(shortcutFor(key({ key: 'k' }), ctx)).toBeNull()
  })
})
