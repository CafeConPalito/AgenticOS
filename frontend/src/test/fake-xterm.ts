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
    Terminal.instances.push(this)
  }

  loadAddon() {}
  open() {}
  reset() {
    this.output = ''
  }
  write(data: string) {
    this.output += data
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
