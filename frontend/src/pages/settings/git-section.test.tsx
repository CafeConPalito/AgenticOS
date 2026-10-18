import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

async function section() {
  renderApp('/ajustes')
  return within(await screen.findByRole('region', { name: es.settings.git.title }))
}

describe('Ajustes › Git', () => {
  it('saves a global setting and removes it when it is emptied', async () => {
    const backend = createFakeBackend({ globalConfig: { 'user.name': 'Ana' } })
    const user = userEvent.setup()
    const git = await section()

    const name = await git.findByRole('textbox', { name: 'user.name' })
    expect(name).toHaveValue('Ana')
    await user.clear(name)
    await user.type(name, 'Ana Díaz')
    await user.click(git.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/git/config')[0].body).toEqual({
        scope: 'global',
        key: 'user.name',
        value: 'Ana Díaz',
      }),
    )
  })

  it('lists the SSH keys and generates a new one', async () => {
    const backend = createFakeBackend({
      sshKeys: [
        {
          name: 'id_ed25519',
          path: '~/.ssh/id_ed25519',
          type: 'ssh-ed25519',
          comment: 'ana@example.com',
          fingerprint: 'SHA256:xyz',
          public: 'ssh-ed25519 AAAA ana@example.com',
          orphan: false,
        },
      ],
    })
    const user = userEvent.setup()
    const git = await section()

    expect(await git.findByText('id_ed25519')).toBeVisible()
    await user.click(git.getByRole('button', { name: es.settings.git.generate }))
    const form = within(await screen.findByRole('form', { name: es.settings.git.generate }))
    await user.clear(form.getByLabelText(es.settings.git.keyName))
    await user.type(form.getByLabelText(es.settings.git.keyName), 'id_nueva')
    await user.type(form.getByLabelText(es.settings.git.email), 'ana@example.com')
    await user.click(form.getByRole('button', { name: es.settings.git.generateSubmit }))

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/git/ssh-keys')[0].body).toEqual({
        name: 'id_nueva',
        email: 'ana@example.com',
        passphrase: '',
      }),
    )
    expect(await git.findByText('id_nueva')).toBeVisible()
  })

  it('tests the connection to a host', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    const git = await section()
    await user.click(await git.findByRole('button', { name: `${es.settings.git.test} github.com` }))
    expect(await git.findByText('Conectado como ana')).toBeVisible()
    await user.click(git.getByRole('button', { name: `${es.settings.git.test} gitlab.com` }))
    expect(await git.findByText(/No se pudo conectar: Permission denied/)).toBeVisible()
  })

  it('shows which hosts have a token and saves a pasted one', async () => {
    const backend = createFakeBackend({ tokens: ['github.com'] })
    const user = userEvent.setup()
    const git = await section()

    const github = within(await git.findByRole('form', { name: 'github.com' }))
    const gitlab = within(git.getByRole('form', { name: 'gitlab.com' }))
    expect(await github.findByText(es.settings.git.hasToken)).toBeVisible()
    expect(await gitlab.findByText(es.settings.git.noToken)).toBeVisible()

    await user.type(gitlab.getByLabelText(`${es.git.pulls.token} gitlab.com`), 'glpat-x')
    await user.click(gitlab.getByRole('button', { name: es.git.pulls.saveToken }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/git/forge-token')[0].body).toEqual({
        host: 'gitlab.com',
        token: 'glpat-x',
      }),
    )
    expect(await gitlab.findByText(es.settings.git.hasToken)).toBeVisible()
  })
})
