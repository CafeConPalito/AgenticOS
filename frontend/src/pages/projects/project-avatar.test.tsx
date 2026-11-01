import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect, useRef } from 'react'
import { ProjectChip, ProjectMark } from '@/components/agentic/primitives'
import es from '@/i18n/es.json'
import { Providers } from '@/providers'
import { createFakeBackend, makeProject } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

// jsdom has no canvas nor image decoding: the crop itself is checked in the browser.
vi.mock('@/lib/image-crop', async (original) => ({
  ...(await original<typeof import('@/lib/image-crop')>()),
  cropToBlob: vi.fn(async () => new Blob(['crop'], { type: 'image/webp' })),
}))
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

const P = es.projects.photo
const V = es.avatars

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

describe('ProjectMark (phase 24, CA1)', () => {
  const inApp = (ui: React.ReactNode) => render(<Providers>{ui}</Providers>)

  it('shows the photo, the initial from 24 px or the colour square', async () => {
    createFakeBackend()
    inApp(
      <>
        <ProjectMark name="Foto" color="#8FB4FF" avatar="photo:0123456789ab" size={40} />
        <ProjectMark name="Tienda" color="#8FB4FF" avatar={null} size={40} />
        <ProjectMark name="Blog" color="#8FB4FF" avatar={null} />
      </>,
    )
    await waitFor(() =>
      expect(
        screen.getByRole('img', { name: 'Foto' }).querySelector('img')!.getAttribute('src'),
      ).toMatch(/\/api\/avatars\/0123456789ab\.webp$/),
    )
    expect(screen.getByRole('img', { name: 'Tienda' })).toHaveTextContent('T')
    const marks = screen.getAllByTestId('project-mark')
    expect(marks[2]).toBeEmptyDOMElement()
    expect(marks[2]).toHaveAttribute('aria-hidden', 'true')
  })

  it('a chip finds the photo of a project known only by its id', async () => {
    createFakeBackend({
      projects: [makeProject({ id: 'p1', name: 'Tienda', avatar: 'photo:0123456789ab' })],
    })
    inApp(<ProjectChip name="Tienda" color="#8FB4FF" projectId="p1" />)
    await waitFor(() =>
      expect(screen.getByTestId('project-mark').querySelector('img')!.getAttribute('src')).toMatch(
        /0123456789ab\.webp$/,
      ),
    )
  })
})

describe('the project photo in its settings (phase 24, CA1)', () => {
  async function openSettings(avatar: string | null = null) {
    const backend = createFakeBackend({
      projects: [makeProject({ id: 'p1', name: 'Tienda', avatar })],
    })
    const user = userEvent.setup()
    renderApp('/proyectos/p1/settings')
    return { backend, user }
  }

  it('frames a photo without owls and sends only the crop', async () => {
    const { backend, user } = await openSettings()
    await user.click(await screen.findByRole('button', { name: P.add }))
    const dialog = await screen.findByRole('dialog', {
      name: V.title.replace('{{name}}', 'Tienda'),
    })
    expect(within(dialog).queryByRole('tab', { name: V.tabs.owls })).toBeNull()
    expect(within(dialog).getByText(V.photoOnlyDescription)).toBeVisible()
    await user.upload(within(dialog).getByLabelText(V.photo.file), png(1200, 900))
    await user.click(await within(dialog).findByRole('button', { name: V.photo.use }))
    await waitFor(() => expect(backend.avatarUploads).toHaveLength(1))
    expect(backend.avatarUploads[0].agentId).toBe('p1')
    expect(await backend.avatarUploads[0].body!.text()).toBe('crop')
    expect(await screen.findByText(P.saved)).toBeVisible()
  })

  it('removes the photo', async () => {
    const { backend, user } = await openSettings('photo:0123456789ab')
    await user.click(await screen.findByRole('button', { name: P.remove }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/projects/p1').at(-1)?.body).toEqual({ avatar: null }),
    )
  })
})

describe('the photo of a new project (phase 24, CA1)', () => {
  it('waits in memory and is uploaded once the project exists', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/proyectos/nuevo')
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(es.projects.fields.path), 'D:\\proyectos\\web')
    await user.click(within(dialog).getByRole('button', { name: P.add }))
    const photo = await screen.findByRole('dialog', { name: V.title.replace('{{name}}', 'web') })
    await user.upload(within(photo).getByLabelText(V.photo.file), png(800, 800))
    await user.click(await within(photo).findByRole('button', { name: V.photo.use }))
    await waitFor(() => expect(screen.getAllByRole('dialog')).toHaveLength(1))
    expect(backend.avatarUploads).toEqual([])
    await user.click(within(dialog).getByRole('button', { name: es.projects.new.submit }))
    await waitFor(() => expect(backend.avatarUploads).toHaveLength(1))
    const created = backend.callsTo('POST', '/api/projects')[0]
    expect(created.body).not.toHaveProperty('avatar')
    expect(await backend.avatarUploads[0].body!.text()).toBe('crop')
  })
})
