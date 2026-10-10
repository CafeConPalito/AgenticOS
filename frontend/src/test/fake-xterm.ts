/**
 * xterm.js stand-in for jsdom (no canvas/layout). Use with
 * `vi.mock('@xterm/xterm', () => import('@/test/fake-xterm'))`.
 */
export class Terminal {
  static instances: Terminal[] = []
  options: Record<string, unknown>
  output = ''
  cols = 100
  rows = 30
  focused = false
  disposed = false
  private dataListeners: ((data: string) => void)[] = []

  constructor(options: Record<string, unknown> = {}) {
    this.options = { ...options }
    if (typeof options.cols === 'number') this.cols = options.cols
    if (typeof options.rows === 'number') this.rows = options.rows
    Terminal.instances.push(this)
  }

  loadAddon() {}
  open() {}
  reset() {
    this.output = ''
  }
  write(data: string, callback?: () => void) {
    this.output += data
    callback?.()
  }
  resize(cols: number, rows: number) {
    this.cols = cols
    this.rows = rows
  }
  focus() {
    this.focused = true
  }
  dispose() {
    this.disposed = true
  }
  onData(listener: (data: string) => void) {
    this.dataListeners.push(listener)
    return {
      dispose: () => {
        this.dataListeners = this.dataListeners.filter((l) => l !== listener)
      },
    }
  }

  /** Simulates the user typing in the terminal. */
  type(data: string) {
    this.dataListeners.forEach((l) => l(data))
  }
}
