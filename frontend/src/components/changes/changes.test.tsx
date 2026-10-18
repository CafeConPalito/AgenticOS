import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ChangesTarget, FileDiff, RepoChanges } from '@/api/changes'
import es from '@/i18n/es.json'
import { Providers } from '@/providers'
import {
  createFakeBackend,
  diffLine,
  makeChanges,
  makeFileChange,
  makeRepoChanges,
} from '@/test/fake-backend'
import { TaskChanges } from './ChangesSheet'
import { ChangesViewer } from './ChangesViewer'

const RUN: ChangesTarget = { kind: 'run', id: 'r1' }

/** The text of a row's cells (the marker one is aria-hidden, so roles would skip it). */
const cells = (row: HTMLElement) =>
  Array.from((row as HTMLTableRowElement).cells).map((cell) => cell.textContent)

function show(target: ChangesTarget = RUN) {
  return render(
    <Providers>
      <ChangesViewer target={target} />
    </Providers>,
  )
}

const login: FileDiff = {
  path: 'src/app.py',
  binary: false,
  too_large: false,
  hunks: [
    {
      old_start: 1,
      old_lines: 3,
      new_start: 1,
      new_lines: 4,
      header: 'def login()',
      lines: [
        diffLine('context', 'import os', 1, 1),
        diffLine('del', 'x = 1', 2, null),
        diffLine('add', 'x = 2', null, 2),
        diffLine('add', 'y = 3', null, 3),
        diffLine('context', 'return x', 3, 4),
      ],
    },
  ],
}

describe('ChangesViewer', () => {
  it('shows the header, the list of files and the diff of each one', async () => {
    const app = makeFileChange({ path: 'src/app.py', additions: 2, deletions: 1 })
    const logo = makeFileChange({ path: 'README.md', status: 'added', additions: 1 })
    createFakeBackend({
      changes: {
        'run:r1': {
          summary: makeChanges({ files: [app, logo] }),
          diffs: {
            'src/app.py': login,
            'README.md': {
              path: 'README.md',
              binary: false,
              too_large: false,
              hunks: [
                {
                  old_start: 0,
                  old_lines: 0,
                  new_start: 1,
                  new_lines: 1,
                  header: '',
                  lines: [diffLine('add', 'hola', null, 1)],
                },
              ],
            },
          },
        },
      },
    })
    show()

    expect(await screen.findByText('2 ficheros')).toBeVisible()
    expect(screen.getByText('rama base «main» → «agentic/T-1»')).toBeVisible()
    const list = screen.getByRole('list', { name: es.changes.fileList })
    expect(within(list).getByText('src/app.py')).toBeVisible()
    expect(within(list).getByLabelText(es.changes.status.added)).toBeVisible()

    const file = screen.getByRole('region', { name: 'src/app.py' })
    expect(await within(file).findByText('x = 2')).toBeVisible()
    expect(within(file).getByText('x = 1')).toBeVisible()
    expect(within(file).getByText('def login()', { exact: false })).toBeVisible()
    // Old and new line numbers, like `git diff`.
    const row = within(file).getByText('x = 2').closest('tr')!
    expect(cells(row)).toEqual(['', '2', '+', 'x = 2'])
    const deleted = within(file).getByText('x = 1').closest('tr')!
    expect(cells(deleted)).toEqual(['2', '', '−', 'x = 1'])
  })

  it('folds the generated files and loads their diff only when opened', async () => {
    const lock = makeFileChange({ path: 'uv.lock', additions: 1, generated: true })
    const backend = createFakeBackend({
      changes: {
        'run:r1': {
          summary: makeChanges({ files: [lock] }),
          diffs: {
            'uv.lock': {
              path: 'uv.lock',
              binary: false,
              too_large: false,
              hunks: [
                {
                  old_start: 0,
                  old_lines: 0,
                  new_start: 1,
                  new_lines: 1,
                  header: '',
                  lines: [diffLine('add', 'version = 1', null, 1)],
                },
              ],
            },
          },
        },
      },
    })
    const user = userEvent.setup()
    show()

    const file = await screen.findByRole('region', { name: 'uv.lock' })
    expect(within(file).getByText(es.changes.foldedGenerated)).toBeVisible()
    expect(backend.calls.filter((c) => c.path.endsWith('/changes/file'))).toHaveLength(0)

    await user.click(within(file).getByRole('button', { expanded: false }))

    expect(await within(file).findByText('version = 1')).toBeVisible()
    expect(backend.calls.filter((c) => c.path.endsWith('/changes/file'))).toHaveLength(1)
  })

  it('folds a very large diff too', async () => {
    const big = makeFileChange({ path: 'data.json', additions: 700, deletions: 200 })
    const backend = createFakeBackend({
      changes: { 'run:r1': { summary: makeChanges({ files: [big] }) } },
    })
    show()

    const file = await screen.findByRole('region', { name: 'data.json' })
    expect(within(file).getByText('900 líneas cambiadas')).toBeVisible()
    expect(backend.calls.filter((c) => c.path.endsWith('/changes/file'))).toHaveLength(0)
  })

  it('shows binary files with their size and a diff that is too large without content', async () => {
    const logo = makeFileChange({
      path: 'logo.png',
      binary: true,
      old_size: 3,
      new_size: 2048,
    })
    const huge = makeFileChange({ path: 'huge.txt', additions: 5 })
    createFakeBackend({
      changes: {
        'run:r1': {
          summary: makeChanges({ files: [logo, huge] }),
          diffs: { 'huge.txt': { path: 'huge.txt', binary: false, too_large: true, hunks: [] } },
        },
      },
    })
    show()

    const binary = await screen.findByRole('region', { name: 'logo.png' })
    expect(within(binary).getByText('Binario · 3 B → 2 kB')).toBeVisible()
    const large = screen.getByRole('region', { name: 'huge.txt' })
    expect(await within(large).findByText(es.changes.tooLarge)).toBeVisible()
  })

  it('widens the context between hunks, a step at a time, with the right line numbers', async () => {
    const app = makeFileChange({ path: 'app.py', additions: 2, deletions: 0 })
    const hunk = (start: number, text: string) => ({
      old_start: start,
      old_lines: 3,
      new_start: start,
      new_lines: 4,
      header: '',
      lines: [
        diffLine('context', `ctx ${start}`, start, start),
        diffLine('add', text, null, start + 1),
        diffLine('context', `ctx ${start + 1}`, start + 1, start + 2),
        diffLine('context', `ctx ${start + 2}`, start + 2, start + 3),
      ],
    })
    // Hunks cover 1-4 and 40-43 of the new file: 35 lines in between (5-39) and 18 after.
    const lines = Array.from({ length: 60 }, (_, n) =>
      diffLine('context', `linea ${n + 1}`, null, n + 1),
    )
    const backend = createFakeBackend({
      changes: {
        'run:r1': {
          summary: makeChanges({ files: [app] }),
          diffs: {
            'app.py': {
              path: 'app.py',
              binary: false,
              too_large: false,
              hunks: [hunk(1, 'primera'), hunk(40, 'segunda')],
            },
          },
          lines,
        },
      },
    })
    const user = userEvent.setup()
    show()

    const file = await screen.findByRole('region', { name: 'app.py' })
    await user.click(await within(file).findByRole('button', { name: 'Mostrar 20 líneas más' }))
    const first = await within(file).findByText('linea 5')
    expect(within(file).getByText('linea 24')).toBeVisible()
    expect(within(file).queryByText('linea 25')).toBeNull()
    // The old number follows from the hunk before: one line was added, so old = new − 1.
    expect(cells(first.closest('tr')!)[0]).toBe('4')
    expect(backend.calls.filter((c) => c.path.endsWith('/lines'))[0].query).toContain(
      'start=5&end=24',
    )

    await user.click(await within(file).findByRole('button', { name: 'Mostrar 15 líneas más' }))
    expect(await within(file).findByText('linea 39')).toBeVisible()
    expect(within(file).queryByRole('button', { name: /Mostrar \d+ líneas más/ })).toBeNull()

    await user.click(within(file).getByRole('button', { name: es.changes.showMoreAfter }))
    expect(await within(file).findByText('linea 60')).toBeVisible()
    // Fewer lines than asked for: the file ended.
    await waitFor(() =>
      expect(within(file).queryByRole('button', { name: es.changes.showMoreAfter })).toBeNull(),
    )
  })

  it('explains why there is no diff', async () => {
    for (const state of ['no_git', 'no_snapshots', 'snapshot_missing'] as const) {
      createFakeBackend({
        changes: { 'run:r1': { summary: makeChanges({ state, files: [], from_ref: null }) } },
      })
      const { unmount } = show()
      expect(await screen.findByText(es.changes.empty[state].title)).toBeVisible()
      expect(screen.getByText(es.changes.empty[state].description)).toBeVisible()
      unmount()
    }
    createFakeBackend({ changes: { 'run:r1': { summary: makeChanges({ files: [] }) } } })
    show()
    expect(await screen.findByText(es.changes.empty.none)).toBeVisible()
  })

  it('warns about live runs, interrupted ones, a shared folder and what was left out', async () => {
    createFakeBackend({
      changes: {
        'run:r1': {
          summary: makeChanges({
            live: true,
            partial: true,
            direct_folder: true,
            skipped_large: 2,
            truncated_files: 3,
            from_ref: { kind: 'run_start', name: '' },
            to_ref: { kind: 'now', name: '' },
          }),
        },
      },
    })
    show()

    expect(await screen.findByText(es.changes.live)).toBeVisible()
    expect(screen.getByText(es.changes.partial)).toBeVisible()
    expect(screen.getByText(es.changes.directFolder)).toBeVisible()
    expect(screen.getByText('2 ficheros nuevos de más de 5 MB no se incluyen.')).toBeVisible()
    expect(screen.getByText('Hay 3 ficheros más que no se muestran.')).toBeVisible()
    expect(screen.getByText('inicio de la ejecución → ahora')).toBeVisible()
  })
})

describe('TaskChanges', () => {
  it('shows the whole task and lets you pick what one run changed', async () => {
    const whole = makeChanges({
      files: [makeFileChange({ path: 'a.py' }), makeFileChange({ path: 'b.py' })],
      runs: [
        {
          id: 'run-dev',
          stage_name: 'Desarrollo',
          attempt: 1,
          status: 'completed',
          started_at: '2026-10-15T10:00:00Z',
          created_at: '2026-10-15T10:00:00Z',
          totals: { files: 1, additions: 1, deletions: 0 },
        },
        {
          id: 'run-qa',
          stage_name: 'QA',
          attempt: 1,
          status: 'completed',
          started_at: '2026-10-15T11:00:00Z',
          created_at: '2026-10-15T11:00:00Z',
          totals: { files: 1, additions: 4, deletions: 2 },
        },
      ],
    })
    const backend = createFakeBackend({
      changes: {
        'task:t1': { summary: whole },
        'run:run-qa': {
          summary: makeChanges({
            files: [makeFileChange({ path: 'tests/test_a.py', additions: 4, deletions: 2 })],
            from_ref: { kind: 'run_start', name: '' },
            to_ref: { kind: 'run_end', name: '' },
          }),
        },
      },
    })
    const user = userEvent.setup()
    render(
      <Providers>
        <TaskChanges taskId="t1" />
      </Providers>,
    )

    const list = await screen.findByRole('list', { name: es.changes.fileList })
    expect(within(list).getByText('a.py')).toBeVisible()
    expect(within(list).getByText('b.py')).toBeVisible()

    await user.click(screen.getByRole('combobox', { name: es.changes.show }))
    await user.click(await screen.findByRole('option', { name: /QA · intento 1/ }))

    const only = await screen.findByRole('list', { name: es.changes.fileList })
    await waitFor(() => expect(within(only).getByText('tests/test_a.py')).toBeVisible())
    expect(within(only).queryByText('a.py')).toBeNull()
    expect(backend.callsTo('GET', '/api/runs/run-qa/changes')).toHaveLength(1)
  })

  it('has no selector when the task has a single run', async () => {
    createFakeBackend({ changes: { 'task:t1': { summary: makeChanges() } } })
    render(
      <Providers>
        <TaskChanges taskId="t1" />
      </Providers>,
    )

    expect(await screen.findByRole('list', { name: es.changes.fileList })).toBeVisible()
    expect(screen.queryByRole('combobox')).toBeNull()
  })
})

describe('ChangesViewer with several repositories', () => {
  const hunk = (text: string): FileDiff['hunks'] => [
    {
      old_start: 0,
      old_lines: 0,
      new_start: 1,
      new_lines: 1,
      header: '',
      lines: [diffLine('add', text, null, 1)],
    },
  ]

  it('groups the files by repository and asks each diff of its own repository', async () => {
    const api = makeRepoChanges('backend', [makeFileChange({ path: 'api.py', additions: 2 })])
    const ui = makeRepoChanges('frontend', [makeFileChange({ path: 'api.py', additions: 1 })])
    const backend = createFakeBackend({
      changes: {
        'run:r1': {
          summary: makeChanges({
            repos: [api, ui],
            totals: { files: 2, additions: 3, deletions: 0 },
          }),
          // The same path in two repositories: each one has its own diff.
          diffs: {
            'repo-backend:api.py': {
              path: 'api.py',
              binary: false,
              too_large: false,
              hunks: hunk('def login(): pass'),
            },
            'repo-frontend:api.py': {
              path: 'api.py',
              binary: false,
              too_large: false,
              hunks: hunk('export const api = 1'),
            },
          },
        },
      },
    })
    show()

    expect(await screen.findByRole('heading', { name: 'backend' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'frontend' })).toBeVisible()
    expect(screen.getByText('2 ficheros')).toBeVisible() // the total of both

    const backendSection = screen.getByRole('region', { name: 'backend' })
    const frontendSection = screen.getByRole('region', { name: 'frontend' })
    expect(await within(backendSection).findByText('def login(): pass')).toBeVisible()
    expect(await within(frontendSection).findByText('export const api = 1')).toBeVisible()
    const asked = backend.calls
      .filter((c) => c.path.endsWith('/changes/file'))
      .map((c) => new URLSearchParams(c.query).get('repo'))
    expect(asked.sort()).toEqual(['repo-backend', 'repo-frontend'])
  })

  it('shows a repository without a diff next to the ones that have one', async () => {
    const api = makeRepoChanges('backend', [makeFileChange({ path: 'api.py', additions: 2 })])
    const empty: RepoChanges = { ...makeRepoChanges('docs', []), state: 'snapshot_missing' }
    createFakeBackend({
      changes: {
        'run:r1': {
          summary: makeChanges({ repos: [api, empty], totals: api.totals }),
          diffs: {},
        },
      },
    })
    show()

    expect(await screen.findByRole('heading', { name: 'backend' })).toBeVisible()
    const docs = screen.getByRole('region', { name: 'docs' })
    expect(within(docs).getByRole('note')).toHaveTextContent(
      es.changes.empty.snapshot_missing.title,
    )
  })
})
