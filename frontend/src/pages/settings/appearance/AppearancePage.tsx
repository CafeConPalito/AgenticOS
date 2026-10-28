import { Check, Copy, Download, MoreHorizontal, Pencil, Trash2, Upload } from 'lucide-react'
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
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { Segmented } from '@/pages/usage/parts'
import { BUILTIN_IDS } from '@/theme/builtin'
import type { Appearance, ThemeDefinition } from '@/theme/model'
import { resolveTheme } from '@/theme/resolve'
import { useTheme } from '@/theme/ThemeProvider'
import { downloadTheme, freeId, parseTheme, withoutTheme } from './theme-io'
import { ThemeSwatch } from './ThemeSwatch'

interface ThemeEntry {
  id: string
  name: string
  custom?: ThemeDefinition
}

/** Ajustes › Apariencia (phase 20): the theme on screen, the gallery and the person's themes. */
export default function AppearancePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { appearance, setAppearance, resolved } = useTheme()
  const fileRef = useRef<HTMLInputElement>(null)
  const [deleting, setDeleting] = useState<ThemeDefinition | null>(null)
  const a = 'appearance'

  const themes = useMemo<ThemeEntry[]>(
    () => [
      ...BUILTIN_IDS.map((id) => ({ id, name: t(`${a}.builtin.${id}`) })),
      ...appearance.custom.map((custom) => ({ id: custom.id, name: custom.name, custom })),
    ],
    [appearance.custom, t],
  )
  const nameOf = (id: string) => themes.find((x) => x.id === id)?.name ?? id

  function use(id: string) {
    setAppearance({ ...appearance, mode: 'fixed', theme: id })
  }

  /** A new theme of the person's own, starting from `source`; opens the editor. */
  function duplicate(source: ThemeEntry) {
    const name = t(`${a}.copyName`, { name: source.name })
    const id = freeId(
      name,
      appearance.custom.map((c) => c.id),
    )
    const base = resolveTheme(source.id, appearance.custom).base
    const theme: ThemeDefinition = {
      format: 'agentic-os.theme',
      version: 1,
      id,
      name,
      base,
      extends: source.id,
      colors: {},
    }
    setAppearance({ ...appearance, custom: [...appearance.custom, theme] })
    void navigate(`/ajustes/apariencia/${id}`)
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
          </>
        }
      />

      <section
        aria-labelledby="appearance-mode"
        className="flex flex-col gap-3 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
      >
        <h2 id="appearance-mode" className="text-[15px] font-medium">
          {t(`${a}.mode.title`)}
        </h2>
        <div className="self-start">
          <Segmented<Appearance['mode']>
            label={t(`${a}.mode.title`)}
            value={appearance.mode}
            onChange={(mode) => setAppearance({ ...appearance, mode })}
            options={(['fixed', 'system'] as const).map((value) => ({
              value,
              label: t(`${a}.mode.${value}`),
            }))}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          {appearance.mode === 'fixed'
            ? t(`${a}.mode.fixedHelp`, { name: nameOf(appearance.theme) })
            : t(`${a}.mode.systemHelp`)}
        </p>
        {appearance.mode === 'system' && (
          <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
            {(['light_theme', 'dark_theme'] as const).map((field) => (
              <div key={field} className="flex flex-col gap-1.5">
                <Label htmlFor={field}>{t(`${a}.mode.${field}`)}</Label>
                <Select
                  value={appearance[field]}
                  onValueChange={(id) => setAppearance({ ...appearance, [field]: id })}
                >
                  <SelectTrigger id={field} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {themes.map((theme) => (
                      <SelectItem key={theme.id} value={theme.id}>
                        {theme.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="appearance-themes" className="flex flex-col gap-3">
        <h2 id="appearance-themes" className="text-[15px] font-medium">
          {t(`${a}.themes`)}
        </h2>
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
          {themes.map((theme) => {
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
                        <DropdownMenuItem onSelect={() => downloadTheme(theme.custom!)}>
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
