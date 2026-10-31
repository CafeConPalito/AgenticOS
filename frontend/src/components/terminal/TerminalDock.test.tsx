import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAccount, makeProject, makeRun } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'
import { DOCK_DEFAULTS, useDock } from './dock-store'
import { folderName } from './TerminalDock'

vi.mock('@xterm/xterm', () => import('@/test/fake-xterm'))
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() {}
  },
}))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

beforeEach(() => {
  useDock.setState({ ...DOCK_DEFAULTS })
})

const D = es.dock
// By its attribute: an open dialog hides the rest of the page from the accessibility tree.
const dock = () => document.querySelector<HTMLElement>('[data-terminal-dock]')

describe('TerminalDock (phase 23: terminals of one\u2019s own)', () => {
  it('the header button and Ctrl+` toggle it; with no terminal it asks for one', async () => {
    createFakeBackend()
    installFakeWebSocket()
    const user = userEvent.setup()
    renderApp('/agentes')
    const button = await screen.findByRole('button', { name: D.toggle })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(dock()).not.toBeInTheDocument()

    await user.click(button)
    expect(dock()).toBeInTheDocument()
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findByRole('dialog', { name: D.new.title })).toBeVisible()
    await user.keyboard('{Escape}')
    expect(await within(dock()!).findByText(D.empty)).toBeVisible()
    expect(JSON.parse(localStorage.getItem('agentic-os.dock')!).state.open).toBe(true)

    act(() => {
      fireEvent.keyDown(window, { key: 'º', code: 'Backquote', ctrlKey: true })
    })
    expect(dock()).not.toBeInTheDocument()
    act(() => {
      fireEvent.keyDown(window, { key: 'º', code: 'Backquote', ctrlKey: true })
    })
    expect(dock()).toBeInTheDocument()
  })

  it('opens a CLI with the chosen account in a project, the personal or any folder (CA2)', async () => {
    const work = makeAccount({ cli: 'claude', name: 'trabajo@empresa.com', is_default: false })
    const project = makeProject({ name: 'Tienda', path: 'D:\\code\\tienda' })
    const backend = createFakeBackend({ accounts: [work], projects: [project] })
    installFakeWebSocket()
    useDock.setState({ open: true })
    const user = userEvent.setup()
    renderApp('/')

    let dialog = await screen.findByRole('dialog', { name: D.new.title })
    await user.click(within(dialog).getByRole('combobox', { name: D.new.account }))
    await user.click(await screen.findByRole('option', { name: 'trabajo@empresa.com' }))
    await user.click(within(dialog).getByRole('radio', { name: D.new.places.project }))
    await user.click(within(dialog).getByRole('button', { name: D.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/terminals')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/terminals')[0].body).toEqual({
      cli: 'claude',
      account_id: work.id,
      cwd: 'D:\\code\\tienda',
    })
    const tabs = await within(dock()!).findAllByRole('tab')
    expect(tabs[0]).toHaveTextContent('trabajo@empresa.com · tienda')

    // Another, in any folder of the system.
    await user.click(within(dock()!).getByRole('button', { name: D.new.open }))
    dialog = await screen.findByRole('dialog', { name: D.new.title })
    await user.click(within(dialog).getByRole('radio', { name: D.new.places.other }))
    await user.type(within(dialog).getByPlaceholderText(es.folderPicker.placeholder), 'E:\\notas')
    await user.click(within(dialog).getByRole('button', { name: D.new.submit }))
    await waitFor(() => expect(within(dock()!).getAllByRole('tab')).toHaveLength(2))
    expect(backend.callsTo('POST', '/api/terminals')[1].body).toMatchObject({ cwd: 'E:\\notas' })
  })

  it('several terminals in tabs: the shown one has the keyboard, they stay on navigating and close with their tab (CA3)', async () => {
    const first = makeRun({
      kind: 'terminal',
      agent_id: null,
      cwd: 'C:\\Users\\yo',
      account_label: 'Personal',
    })
    const second = makeRun({
      kind: 'terminal',
      agent_id: null,
      cwd: 'D:\\web',
      account_label: 'Trabajo',
    })
    // An agent's run is not here any more: it is in Ejecuciones.
    const agentRun = makeRun({ prompt: 'Tarea del agente' })
    const backend = createFakeBackend({ runs: [first, second, agentRun] })
    const Socket = installFakeWebSocket()
    useDock.setState({ open: true })
    const user = userEvent.setup()
    const { router } = renderApp('/')

    const tabs = await within(dock()!).findAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual([
      'Claude CodePersonal · yo',
      'Claude CodeTrabajo · web',
    ])
    expect(within(tabs[0]).getByRole('img', { name: 'Claude Code' })).toBeInTheDocument()
    await waitFor(() => expect(Socket.instances.at(-1)?.url).toContain(`/runs/${first.id}/`))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/runs/${first.id}/control`)[0]?.body).toMatchObject({
        action: 'take',
      }),
    )

    await user.click(tabs[1])
    await waitFor(() => expect(Socket.instances.at(-1)?.url).toContain(`/runs/${second.id}/`))
    // The tab left gives the keyboard back.
    expect(backend.callsTo('POST', `/api/runs/${first.id}/control`).at(-1)?.body).toMatchObject({
      action: 'release',
    })

    await router.navigate('/tablero')
    expect(within(dock()!).getAllByRole('tab')).toHaveLength(2)

    await user.click(
      within(dock()!).getByRole('button', {
        name: D.closeTab.replace('{{name}}', 'Personal · yo'),
      }),
    )
    await waitFor(() => expect(within(dock()!).getAllByRole('tab')).toHaveLength(1))
    expect(backend.callsTo('DELETE', `/api/terminals/${first.id}`)).toHaveLength(1)
  })

  it('docks to the right and back, and hides', async () => {
    createFakeBackend({ runs: [makeRun({ kind: 'terminal', agent_id: null })] })
    installFakeWebSocket()
    useDock.setState({ open: true })
    const user = userEvent.setup()
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: D.toRight }))
    expect(dock()).toHaveClass('w-[480px]')
    await user.click(screen.getByRole('button', { name: D.toBottom }))
    expect(dock()).toHaveClass('h-[300px]')
    await user.click(screen.getByRole('button', { name: D.close }))
    expect(dock()).not.toBeInTheDocument()
  })

  it('names a tab after its folder', () => {
    expect(folderName('D:\\code\\web\\')).toBe('web')
    expect(folderName('/home/yo/notas')).toBe('notas')
    expect(folderName('~')).toBe('~')
  })
})
