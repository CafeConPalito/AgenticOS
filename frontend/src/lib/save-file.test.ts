import { saveFile } from './save-file'

const tauri = vi.hoisted(() => ({
  on: false,
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}))
vi.mock('@tauri-apps/api/core', async (original) => ({
  ...(await original<typeof import('@tauri-apps/api/core')>()),
  isTauri: () => tauri.on,
  invoke: (cmd: string, args?: unknown) => tauri.invoke(cmd, args),
}))

const request = {
  name: 'Redactor.agent.json',
  text: '{"name":"Redactor"}',
  type: 'application/json',
  filter: 'Agente',
  extensions: ['json'],
}

afterEach(() => {
  tauri.on = false
  tauri.invoke.mockReset()
})

describe('saveFile (phase 21, CA4)', () => {
  it('in the desktop app the shell asks where and writes it: no blob download', async () => {
    tauri.on = true
    tauri.invoke.mockResolvedValue('C:\\Users\\u\\Redactor.agent.json')
    const createObjectURL = vi.fn(() => 'blob:x')
    URL.createObjectURL = createObjectURL

    await expect(saveFile(request)).resolves.toBe('C:\\Users\\u\\Redactor.agent.json')
    expect(tauri.invoke).toHaveBeenCalledWith('save_file', {
      name: 'Redactor.agent.json',
      contents: '{"name":"Redactor"}',
      filter: 'Agente',
      extensions: ['json'],
    })
    expect(createObjectURL).not.toHaveBeenCalled()
  })

  it('cancelling the dialog gives null', async () => {
    tauri.on = true
    tauri.invoke.mockResolvedValue(null)
    await expect(saveFile(request)).resolves.toBeNull()
  })

  it('in the browser it is a download', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    await expect(saveFile(request)).resolves.toBeUndefined()
    expect(click).toHaveBeenCalled()
    expect(tauri.invoke).not.toHaveBeenCalled()
    click.mockRestore()
  })
})
