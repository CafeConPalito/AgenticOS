import { AlertTriangle, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { PageContainer, PageHeader } from '@/components/page'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
import { contrastIssues } from '@/theme/contrast'
import {
  BASE_TOKENS,
  type Base,
  DENSITIES,
  type Density,
  FONTS,
  type Font,
  type ThemeDefinition,
  type TokenName,
} from '@/theme/model'
import { resolveTheme } from '@/theme/resolve'
import { useTheme } from '@/theme/ThemeProvider'
import { TOKEN_GROUPS } from './theme-io'
import { ThemePreview } from './ThemePreview'

const HEX = /^#[0-9a-fA-F]{6}$/
/** The «extends none» item: Radix Select cannot use "" as a value. */
const NONE = '__none__'
const ratio = (value: number) => value.toLocaleString('es-ES', { maximumFractionDigits: 1 })

/** Ajustes › Apariencia › <theme> (phase 20): edit one of the person's themes, live. */
export default function ThemeEditorPage() {
  const { themeId } = useParams()
  const { t } = useTranslation()
  const { appearance } = useTheme()
  const saved = appearance.custom.find((theme) => theme.id === themeId)
  if (!saved)
    return (
      <PageContainer>
        <PageHeader title={t('appearance.editor.missing')} />
        <Link to="/ajustes/apariencia" className="text-sm underline">
          {t('appearance.editor.back')}
        </Link>
      </PageContainer>
    )
  // Keyed: another theme (or the same one saved elsewhere) starts a fresh draft.
  return <Editor key={saved.id} saved={saved} />
}

function Editor({ saved }: { saved: ThemeDefinition }) {
  const { t } = useTranslation()
  const { appearance, setAppearance, preview } = useTheme()
  const [draft, setDraft] = useState<ThemeDefinition>(saved)
  const e = 'appearance.editor'
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved)

  // Memoized: a new array each render would re-resolve the draft and loop with `preview`.
  const others = useMemo(
    () => appearance.custom.filter((theme) => theme.id !== saved.id),
    [appearance.custom, saved.id],
  )
  const resolved = useMemo(() => resolveTheme(draft.id, [...others, draft]), [others, draft])
  // What a color goes back to: the theme it extends, or the base set for one made from scratch.
  const parent = useMemo(
    () => (draft.extends ? resolveTheme(draft.extends, others).colors : BASE_TOKENS[draft.base]),
    [draft.extends, draft.base, others],
  )
  const issues = useMemo(() => contrastIssues(resolved.colors), [resolved.colors])
  const flagged = new Set(issues.flatMap((issue) => [issue.text, issue.background]))

  // The whole app shows the draft while the editor is open (CA7: live preview).
  useEffect(() => {
    preview(resolved)
  }, [preview, resolved])
  useEffect(() => () => preview(null), [preview])

  const set = (changes: Partial<ThemeDefinition>) => setDraft((d) => ({ ...d, ...changes }))
  const setColor = (token: TokenName, value: string | null) =>
    setDraft((d) => {
      const colors = { ...d.colors }
      if (value === null) delete colors[token]
      else colors[token] = value.toLowerCase()
      return { ...d, colors }
    })

  function save(andUse: boolean) {
    const custom = appearance.custom.map((theme) => (theme.id === saved.id ? draft : theme))
    setAppearance({ ...appearance, custom, ...(andUse && { theme: draft.id }) })
  }

  const extendable = [
    ...BUILTIN_IDS.map((id) => ({ id, name: t(`appearance.builtin.${id}`) })),
    ...others.map((theme) => ({ id: theme.id, name: theme.name })),
  ]

  return (
    <PageContainer>
      <UnsavedChangesGuard when={dirty} />
      <PageHeader
        title={draft.name || t(`${e}.untitled`)}
        subtitle={t(`${e}.subtitle`)}
        actions={
          <>
            <Button variant="outline" disabled={!dirty} onClick={() => setDraft(saved)}>
              {t(`${e}.discard`)}
            </Button>
            <Button variant="outline" disabled={!draft.name.trim()} onClick={() => save(true)}>
              {t(`${e}.saveAndUse`)}
            </Button>
            <Button
              disabled={!dirty || !draft.name.trim()}
              onClick={() => save(false)}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              {t('common.save')}
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(320px,440px)] items-start gap-6 max-lg:grid-cols-1">
        <div className="flex flex-col gap-4">
          <section className="flex flex-col gap-3 rounded-xl border border-sep p-4 shadow-card bg-card-grad">
            <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="theme-name">{t(`${e}.name`)}</Label>
                <Input
                  id="theme-name"
                  value={draft.name}
                  maxLength={60}
                  onChange={(ev) => set({ name: ev.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="theme-extends">{t(`${e}.extends`)}</Label>
                <Select
                  value={draft.extends ?? NONE}
                  onValueChange={(id) =>
                    id === NONE
                      ? set({ extends: undefined })
                      : set({ extends: id, base: resolveTheme(id, others).base })
                  }
                >
                  <SelectTrigger id="theme-extends" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>{t(`${e}.extendsNone`)}</SelectItem>
                    {extendable.map((theme) => (
                      <SelectItem key={theme.id} value={theme.id}>
                        {theme.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">{t(`${e}.base`)}</span>
                <Segmented<Base>
                  label={t(`${e}.base`)}
                  value={draft.base}
                  onChange={(base) => set({ base })}
                  options={(['dark', 'light'] as const).map((value) => ({
                    value,
                    label: t(`${e}.bases.${value}`),
                  }))}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="theme-font">{t(`${e}.font`)}</Label>
                <Select value={resolved.font} onValueChange={(font) => set({ font: font as Font })}>
                  <SelectTrigger id="theme-font" className="w-[290px] max-w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FONTS.map((font) => (
                      <SelectItem key={font} value={font}>
                        {t(`${e}.fonts.${font}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">{t(`${e}.density`)}</span>
                <Segmented<Density>
                  label={t(`${e}.density`)}
                  value={resolved.density}
                  onChange={(density) => set({ density })}
                  options={DENSITIES.map((value) => ({
                    value,
                    label: t(`${e}.densities.${value}`),
                  }))}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
              <Range
                id="theme-scale"
                label={t(`${e}.scale`, { value: Math.round(resolved.scale * 100) })}
                hint={t(`${e}.scaleHint`)}
                min={0.8}
                max={1.5}
                step={0.05}
                value={resolved.scale}
                onChange={(scale) => set({ scale })}
              />
              <Range
                id="theme-radius"
                label={t(`${e}.radius`, { value: resolved.radius })}
                min={0}
                max={20}
                step={1}
                value={resolved.radius}
                onChange={(radius) => set({ radius })}
              />
            </div>
          </section>

          {issues.length > 0 && (
            <section
              role="status"
              aria-label={t(`${e}.contrast.title`)}
              className="flex flex-col gap-1.5 rounded-xl border border-status-waiting/50 bg-status-waiting/10 p-3 text-[13px]"
            >
              <p className="flex items-center gap-2 font-medium">
                <AlertTriangle className="size-4 text-status-waiting" />
                {t(`${e}.contrast.title`)}
              </p>
              <ul className="flex flex-col gap-0.5 pl-6 text-muted-foreground">
                {issues.map((issue) => (
                  <li key={`${issue.text}/${issue.background}`}>
                    {t(`${e}.contrast.issue`, {
                      text: t(tokenKey(issue.text)),
                      background: t(tokenKey(issue.background)),
                      ratio: ratio(issue.ratio),
                      minimum: ratio(issue.minimum),
                    })}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {TOKEN_GROUPS.map((group) => (
            <details
              key={group.id}
              open={group.id !== 'terminal' && group.id !== 'charts'}
              className="group rounded-xl border border-sep p-4 shadow-card bg-card-grad"
            >
              <summary className="cursor-pointer text-[14px] font-medium">
                {t(`${e}.groups.${group.id}`)}
              </summary>
              <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-2 max-sm:grid-cols-1">
                {group.tokens.map((token) => (
                  <ColorRow
                    key={token}
                    token={token}
                    value={resolved.colors[token]}
                    inherited={parent[token]}
                    overridden={draft.colors[token] !== undefined}
                    flagged={flagged.has(token)}
                    onChange={(value) => setColor(token, value)}
                  />
                ))}
              </div>
            </details>
          ))}
        </div>
        <div className="sticky top-4 max-lg:static">
          <ThemePreview />
        </div>
      </div>
    </PageContainer>
  )
}

/** The key of a token's name (one per token; the union of 83 is too deep for the typed keys). */
const tokenKey = (token: TokenName) =>
  `appearance.tokens.${token}` as 'appearance.tokens.background'

function ColorRow({
  token,
  value,
  inherited,
  overridden,
  flagged,
  onChange,
}: {
  token: TokenName
  value: string
  inherited: string
  overridden: boolean
  flagged: boolean
  onChange: (value: string | null) => void
}) {
  const { t } = useTranslation()
  const [text, setText] = useState(value)
  const [shown, setShown] = useState(value)
  // A new value from outside (another field, «Restablecer», «Descartar»): show it.
  if (shown !== value) {
    setShown(value)
    setText(value)
  }
  const label = t(tokenKey(token))
  const id = `color-${token}`
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        aria-label={label}
        value={value.slice(0, 7)}
        onChange={(ev) => onChange(ev.target.value)}
        className="h-7 w-9 shrink-0 cursor-pointer rounded border border-input bg-transparent p-0.5"
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <label htmlFor={id} className="flex items-center gap-1 truncate text-[12.5px]">
          {label}
          {flagged && (
            <AlertTriangle
              aria-label={t('appearance.editor.contrast.flag')}
              className="size-3 shrink-0 text-status-waiting"
            />
          )}
        </label>
        <span className="font-mono text-[10.5px] text-muted-foreground">
          {overridden ? token : t('appearance.editor.inherited', { value: inherited })}
        </span>
      </div>
      <Input
        id={id}
        value={text}
        aria-invalid={!HEX.test(text) || undefined}
        onChange={(ev) => {
          setText(ev.target.value)
          if (HEX.test(ev.target.value)) onChange(ev.target.value)
        }}
        onBlur={() => setText(value)}
        className={cn(
          'h-7 w-[92px] font-mono text-[12px]',
          !HEX.test(text) && 'border-destructive',
        )}
      />
      <Button
        type="button"
        size="icon"
        variant="ghost"
        disabled={!overridden}
        aria-label={t('appearance.editor.reset', { name: label })}
        title={t('appearance.editor.reset', { name: label })}
        onClick={() => onChange(null)}
        className="size-7"
      >
        <RotateCcw className="size-3.5" />
      </Button>
    </div>
  )
}

function Range({
  id,
  label,
  hint,
  min,
  max,
  step,
  value,
  onChange,
}: {
  id: string
  label: string
  hint?: string
  min: number
  max: number
  step: number
  value: number
  onChange: (value: number) => void
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(ev) => onChange(Number(ev.target.value))}
        className="accent-primary-action"
      />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}
