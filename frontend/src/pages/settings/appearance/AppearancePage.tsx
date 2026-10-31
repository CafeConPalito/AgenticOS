import { errorMessage } from '@/lib/form-errors'
import { toastSaved } from '@/lib/save-file'
import { Check, Copy, Download, MoreHorizontal, Pencil, Plus, Trash2, Upload } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { PageContainer, PageHeader } from '@/components/page'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { Segmented } from '@/pages/usage/parts'
import { BUILTIN_THEMES, type BuiltinId } from '@/theme/builtin'
import type { Appearance, Base, ThemeDefinition } from '@/theme/model'
import { resolveTheme } from '@/theme/resolve'
import { useTheme } from '@/theme/ThemeProvider'
import { NewThemeDialog } from './NewThemeDialog'
import { downloadTheme, freeId, parseTheme, withoutTheme } from './theme-io'
import { ThemeSwatch } from './ThemeSwatch'

interface ThemeEntry {
  id: string
  name: string
  base: Base
  custom?: ThemeDefinition
}

type Filter = 'all' | Base
const FILTERS: Filter[] = ['all', 'light', 'dark']
/** The gallery filter last chosen in this browser (phase 22). */
export const FILTER_STORAGE_KEY = 'agentic-os.appearance.filter'

/** The filter chosen here before or, the first time, the one of the system's light or dark. */
function initialFilter(): Filter {
  try {
    const stored = localStorage.getItem(FILTER_STORAGE_KEY)
    if (FILTERS.includes(stored as Filter)) return stored as Filter
  } catch {
    // Storage unavailable: the system's.
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/**
 * Ajustes › Apariencia (phases 20 and 22): the gallery of themes, filtered by light or dark,
 * and the person's own themes.
 */
export default function AppearancePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { appearance, setAppearance, resolved } = useTheme()
  const fileRef = useRef<HTMLInputElement>(null)
  const [deleting, setDeleting] = useState<ThemeDefinition | null>(null)
  const [creating, setCreating] = useState(false)
  const [filter, setFilter] = useState<Filter>(initialFilter)
  const a = 'appearance'

  const themes = useMemo<ThemeEntry[]>(() => {
    return [
      ...BUILTIN_THEMES.map(({ id, base }) => ({
        id,
        name: t(`${a}.builtin.${id as BuiltinId}`),
        base,
      })),
      ...appearance.custom.map((custom) => ({
        id: custom.id,
        name: custom.name,
        base: custom.base,
        custom,
      })),
    ]
  }, [appearance.custom, t])
  // The theme in use stays in sight, first, when the filter leaves it out.
  const shown = useMemo(() => {
    if (filter === 'all') return themes
    const matching = themes.filter((theme) => theme.base === filter)
    const current = themes.find((theme) => theme.id === resolved.id)
    return current && current.base !== filter ? [current, ...matching] : matching
  }, [themes, filter, resolved.id])

  function choose(next: Filter) {
    setFilter(next)
    try {
      localStorage.setItem(FILTER_STORAGE_KEY, next)
    } catch {
      // Storage unavailable: chosen for this visit only.
    }
  }

  function use(id: string) {
    setAppearance({ ...appearance, theme: id })
  }

  /** A theme of the person's own; opens the editor. */
  function add(theme: ThemeDefinition) {
    setAppearance({ ...appearance, custom: [...appearance.custom, theme] })
    void navigate(`/ajustes/apariencia/${theme.id}`)
  }

  /** A new theme of the person's own, starting from `source`; opens the editor. */
  function duplicate(source: ThemeEntry) {
    const name = t(`${a}.copyName`, { name: source.name })
    const id = freeId(
      name,
      appearance.custom.map((c) => c.id),
    )
    const base = resolveTheme(source.id, appearance.custom).base
    add({ format: 'agentic-os.theme', version: 2, id, name, base, extends: source.id, colors: {} })
  }

  async function onImport(file: File) {
    const result = parseTheme(await file.text(), appearance)
    if (!result.ok) {
      toast.error(t(`${a}.import.${result.reason}`, { field: result.field }))
      return
    }
    const next: Appearance = { ...appearance, custom: [...appearance.custom, result.theme] }
    setAppearance(next)
    toast.success(t(result.renamed ? `${a}.import.renamed` : `${a}.import.done`, result.theme))
  }

  return (
    <PageContainer>
      <PageHeader
        title={t(`${a}.title`)}
        subtitle={t(`${a}.subtitle`)}
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".json,application/json"
              className="hidden"
              aria-label={t(`${a}.import.label`)}
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file) void onImport(file)
              }}
            />
            <Button variant="outline" onClick={() => fileRef.current?.click()}>
              <Upload />
              {t(`${a}.import.action`)}
            </Button>
            <Button
              onClick={() => setCreating(true)}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              <Plus />
              {t(`${a}.create.action`)}
            </Button>
          </>
        }
      />

      <section aria-labelledby="appearance-themes" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="appearance-themes" className="text-[15px] font-medium">
            {t(`${a}.themes`)}
          </h2>
          <Segmented<Filter>
            label={t(`${a}.filter.label`)}
            value={filter}
            onChange={choose}
            options={FILTERS.map((value) => ({ value, label: t(`${a}.filter.${value}`) }))}
          />
        </div>
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
          {shown.map((theme) => {
            const current = resolved.id === theme.id
            return (
              <li
                key={theme.id}
                aria-label={theme.name}
                aria-current={current ? 'true' : undefined}
                className={cn(
                  'flex flex-col gap-2 rounded-xl border border-sep p-3 shadow-card bg-card-grad',
                  current && 'ring-2 ring-ring',
                )}
              >
                <ThemeSwatch theme={resolveTheme(theme.id, appearance.custom)} />
                <div className="flex items-center gap-1.5">
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
                    {theme.name}
                  </span>
                  {current ? (
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Check className="size-3.5" />
                      {t(`${a}.inUse`)}
                    </span>
                  ) : (
                    <Button size="sm" variant="outline" onClick={() => use(theme.id)}>
                      {t(`${a}.use`)}
                    </Button>
                  )}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={t(`${a}.more`, { name: theme.name })}
                      >
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {theme.custom && (
                        <DropdownMenuItem
                          onSelect={() => void navigate(`/ajustes/apariencia/${theme.id}`)}
                        >
                          <Pencil />
                          {t(`${a}.edit`)}
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuItem onSelect={() => duplicate(theme)}>
                        <Copy />
                        {t(theme.custom ? 'common.duplicate' : `${a}.customize`)}
                      </DropdownMenuItem>
                      {theme.custom && (
                        <DropdownMenuItem
                          onSelect={() =>
                            void downloadTheme(theme.custom!).then(toastSaved, (error: unknown) =>
                              toast.error(errorMessage(error)),
                            )
                          }
                        >
                          <Download />
                          {t(`${a}.export`)}
                        </DropdownMenuItem>
                      )}
                      {theme.custom && (
                        <DropdownMenuItem
                          variant="destructive"
                          onSelect={() => setDeleting(theme.custom!)}
                        >
                          <Trash2 />
                          {t('common.delete')}
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </li>
            )
          })}
        </ul>
      </section>

      <NewThemeDialog
        open={creating}
        onOpenChange={setCreating}
        taken={appearance.custom.map((c) => c.id)}
        defaultBase={filter === 'all' ? resolved.base : filter}
        onCreate={(theme) => {
          setCreating(false)
          add(theme)
        }}
      />

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t(`${a}.delete.title`, { name: deleting?.name })}
        description={t(`${a}.delete.description`)}
        confirmLabel={t('common.delete')}
        destructive
        onConfirm={() => {
          if (deleting) setAppearance(withoutTheme(appearance, deleting.id))
          setDeleting(null)
        }}
      />
    </PageContainer>
  )
}
