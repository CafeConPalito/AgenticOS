import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect, useRef } from 'react'
import es from '@/i18n/es.json'
import { OWLS } from '@/lib/avatars'
import { headerSize, MAX_PHOTO_SIDE } from '@/lib/image-crop'
import { createFakeBackend, makeAgent, makeRun } from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { Providers } from '@/providers'
import { AgentAvatar } from './primitives'

// jsdom has no canvas nor image decoding: the crop itself is checked in the browser (spike S6).
vi.mock('@/lib/image-crop', async (original) => ({
  ...(await original<typeof import('@/lib/image-crop')>()),
  cropToBlob: vi.fn(async () => new Blob(['crop'], { type: 'image/webp' })),
}))
// The cropper needs real image sizes; this one reports a crop once, when it shows.
vi.mock('react-easy-crop', () => ({
  default: function FakeCropper({
    image,
    onCropComplete,
  }: {
    image: string
    onCropComplete: (area: unknown, pixels: unknown) => void
  }) {
    const report = useRef(onCropComplete)
    useEffect(() => report.current({}, { x: 0, y: 0, width: 300, height: 300 }), [])
    return <img alt="cropper" src={image} />
  },
}))

const V = es.avatars
const owlUrl = (id: string) => OWLS.find((owl) => owl.id === id)!.url

/** A PNG whose header says `width` × `height` (the pixels do not matter to the check). */
function png(width: number, height: number): File {
  const bytes = new Uint8Array(64)
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
  const view = new DataView(bytes.buffer)
  view.setUint32(16, width)
  view.setUint32(20, height)
  return new File([bytes], 'foto.png', { type: 'image/png' })
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:local-photo')
  URL.revokeObjectURL = vi.fn()
})

describe('AgentAvatar (phase 20, CA3)', () => {
  const inApp = (ui: React.ReactNode) => render(<Providers>{ui}</Providers>)

  it('shows an owl, a photo or the initial', async () => {
    createFakeBackend()
    inApp(
      <>
        <AgentAvatar name="Búho" color="#8FB4FF" avatar="owl:glasses" />
        <AgentAvatar name="Foto" color="#8FB4FF" avatar="photo:0123456789ab" />
        <AgentAvatar name="Dev" color="#8FB4FF" avatar={null} />
      </>,
    )
    const owl = screen.getByRole('img', { name: 'Búho' })
    expect(owl.querySelector('img')).toHaveAttribute('src', owlUrl('glasses'))
    await waitFor(() =>
      expect(
        screen.getByRole('img', { name: 'Foto' }).querySelector('img')!.getAttribute('src'),
      ).toMatch(/\/api\/avatars\/0123456789ab\.webp$/),
    )
    expect(screen.getByRole('img', { name: 'Dev' })).toHaveTextContent('D')
  })

  it('finds the picture of an agent known only by its id, and falls back if it fails', async () => {
    createFakeBackend({ agents: [makeAgent({ id: 'a1', avatar: 'owl:crown' })] })
    inApp(<AgentAvatar name="Dev" color="#8FB4FF" agentId="a1" />)
    const img = await waitFor(() => {
      const found = screen.getByRole('img', { name: 'Dev' }).querySelector('img')
      expect(found).not.toBeNull()
      return found!
    })
    expect(img).toHaveAttribute('src', owlUrl('crown'))
    img.dispatchEvent(new Event('error'))
    await waitFor(() => expect(screen.getByRole('img', { name: 'Dev' })).toHaveTextContent('D'))
  })

  it('appears on the runs list with the picture of the agent', async () => {
    const agent = makeAgent({ avatar: 'owl:wizard' })
    createFakeBackend({ agents: [agent], runs: [makeRun({ agent_id: agent.id })] })
    renderApp('/ejecuciones')
    await waitFor(() =>
      expect(
        [...document.querySelectorAll('[role="img"] img')].find(
          (img) => img.getAttribute('src') === owlUrl('wizard'),
        ),
        'the run row shows the agent owl',
      ).toBeDefined(),
    )
  })
})

describe('the agent picture in its editor (phase 20, CA4)', () => {
  async function openDialog() {
    const agent = makeAgent({ id: 'a1', name: 'Dev' })
    const backend = createFakeBackend({ agents: [agent] })
    const user = userEvent.setup()
    renderApp('/agentes/a1/general')
    await user.click(await screen.findByRole('button', { name: V.change }))
    const dialog = await screen.findByRole('dialog', { name: V.title.replace('{{name}}', 'Dev') })
    return { backend, user, dialog }
  }

  it('lists the owl gallery and saves one at once', async () => {
    const { backend, user, dialog } = await openDialog()
    const owls = within(dialog).getAllByRole('radio')
    expect(owls).toHaveLength(OWLS.length)
    expect(OWLS.length).toBeGreaterThanOrEqual(12)
    await user.click(within(dialog).getByRole('radio', { name: V.owls.glasses }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/agents/a1').at(-1)?.body).toEqual({
        avatar: 'owl:glasses',
      }),
    )
    expect(await screen.findByText(V.saved)).toBeVisible()
    // Already saved: no pending change for «Guardar cambios».
    expect(screen.getByRole('button', { name: es.common.save })).toBeDisabled()
  })

  it('refuses a photo over 2048 px before decoding it', async () => {
    const { backend, user, dialog } = await openDialog()
    await user.click(within(dialog).getByRole('tab', { name: V.tabs.photo }))
    await user.upload(within(dialog).getByLabelText(V.photo.file), png(3000, 2000))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      V.photo.size.replace('{{max}}', String(MAX_PHOTO_SIDE)),
    )
    expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(backend.avatarUploads).toEqual([])
  })

  it('frames a photo and sends only the crop', async () => {
    const { backend, user, dialog } = await openDialog()
    await user.click(within(dialog).getByRole('tab', { name: V.tabs.photo }))
    await user.upload(within(dialog).getByLabelText(V.photo.file), png(1200, 900))
    expect(await within(dialog).findByAltText('cropper')).toHaveAttribute('src', 'blob:local-photo')
    await user.click(within(dialog).getByRole('button', { name: V.photo.use }))
    await waitFor(() => expect(backend.avatarUploads).toHaveLength(1))
    const sent = backend.avatarUploads[0].body!
    expect(sent.type).toBe('image/webp')
    expect(await sent.text()).toBe('crop')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:local-photo')
  })

  it('goes back to the initials', async () => {
    const { backend, user, dialog } = await openDialog()
    await user.click(within(dialog).getByRole('tab', { name: V.tabs.initials }))
    await user.click(within(dialog).getByRole('button', { name: V.useInitials }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/agents/a1').at(-1)?.body).toEqual({ avatar: null }),
    )
  })
})

describe('image headers (phase 20, spike S6)', () => {
  it('reads PNG, JPEG and WebP sizes, and nothing else', () => {
    expect(headerSize(new Uint8Array(32).buffer)).toBeNull()

    const p = new Uint8Array(32)
    p.set([0x89, 0x50, 0x4e, 0x47])
    new DataView(p.buffer).setUint32(16, 640)
    new DataView(p.buffer).setUint32(20, 480)
    expect(headerSize(p.buffer)).toEqual({ width: 640, height: 480 })

    // JPEG: SOI, then an APP0 segment, then a baseline start of frame (FFC0).
    const j = new Uint8Array(40)
    const jv = new DataView(j.buffer)
    jv.setUint16(0, 0xffd8)
    jv.setUint16(2, 0xffe0)
    jv.setUint16(4, 16)
    jv.setUint16(20, 0xffc0)
    jv.setUint16(22, 17)
    jv.setUint16(25, 900) // height
    jv.setUint16(27, 1600) // width
    expect(headerSize(j.buffer)).toEqual({ width: 1600, height: 900 })

    // WebP (VP8X): 24-bit width-1 and height-1.
    const w = new Uint8Array(40)
    const wv = new DataView(w.buffer)
    w.set([0x52, 0x49, 0x46, 0x46], 0)
    w.set([0x57, 0x45, 0x42, 0x50], 8)
    w.set([0x56, 0x50, 0x38, 0x58], 12)
    wv.setUint32(24, 2999, true)
    wv.setUint32(27, 1999, true)
    expect(headerSize(w.buffer)).toEqual({ width: 3000, height: 2000 })
  })
})
