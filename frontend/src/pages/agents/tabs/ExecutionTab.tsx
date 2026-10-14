import { Check, Hand, Lock, Minus, Plus, RefreshCw, Zap } from 'lucide-react'
import { useState } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useClis, useRefreshClis } from '@/api/clis'
import type { CliId, ModelOption, PermissionMode } from '@/api/types'
import { MAX_CONCURRENCY, PERMISSION_MODES, TOOLS } from '@/api/types'
import { CliTag } from '@/components/agentic/primitives'
import { Field } from '@/components/page'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import i18n from '@/i18n'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import type { AgentFormValues } from '../agent-form'
import { AccountSelect, FallbackFields } from '../AgentLinks'

const CLIS: CliId[] = ['claude', 'agy']
const DEFAULT_MODEL = '__default__' // Radix Select cannot use "" as an item value
const PERMISSION_ICON: Record<PermissionMode, typeof Zap> = {
  autonomous: Zap,
  restricted: Lock,
  ask: Hand,
}

function OptionCard({
  selected,
  onSelect,
  children,
  role = 'radio',
}: {
  selected: boolean
  onSelect: () => void
  children: React.ReactNode
  role?: 'radio' | 'checkbox'
}) {
  return (
    <button
      type="button"
      role={role}
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        'flex items-start gap-2.5 rounded-lg border bg-card p-3 text-left hover:border-ring',
        selected && 'border-ring bg-accent',
      )}
    >
      {children}
    </button>
  )
}

/** The secondary CLI reads and writes the form's two fields together. */
function FallbackWatch() {
  const { setValue } = useFormContext<AgentFormValues>()
  const [cli, accountId, fallbackAccountId, fallbackModel] = useWatch<
    AgentFormValues,
    ['cli', 'account_id', 'fallback_account_id', 'fallback_model']
  >({ name: ['cli', 'account_id', 'fallback_account_id', 'fallback_model'] })
  return (
    <FallbackFields
      idPrefix="agent"
      cli={cli}
      accountId={accountId}
      fallbackAccountId={fallbackAccountId}
      fallbackModel={fallbackModel}
      onChange={(value) => {
        setValue('fallback_account_id', value.fallback_account_id, { shouldDirty: true })
        setValue('fallback_model', value.fallback_model, { shouldDirty: true })
      }}
    />
  )
}

export function ExecutionTab() {
  const { t } = useTranslation()
  const { control, setValue } = useFormContext<AgentFormValues>()
  const cli = useWatch<AgentFormValues, 'cli'>({ name: 'cli' })
  const { data: clis, isPending } = useClis()
  const refresh = useRefreshClis()
  const [refreshing, setRefreshing] = useState(false)
  const info = clis?.find((c) => c.id === cli)
  const modelLabel = (m: ModelOption) => {
    if (m.label) return m.label
    const key = `cli.alias.${m.id}`
    return i18n.exists(key) ? t(key as never) : m.id
  }

  async function onRefresh() {
    setRefreshing(true)
    try {
      await refresh()
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="flex max-w-[1052px] flex-col gap-6 px-6 pt-5 pb-8">
      <div className="grid grid-cols-2 gap-5">
        <Field label={t('agents.fields.cli')}>
          <Controller
            control={control}
            name="cli"
            render={({ field }) => (
              <div
                role="radiogroup"
                aria-label={t('agents.fields.cli')}
                className="grid grid-cols-2 gap-2"
              >
                {CLIS.map((id) => {
                  const detected = clis?.find((c) => c.id === id)
                  return (
                    <OptionCard
                      key={id}
                      selected={field.value === id}
                      onSelect={() => {
                        if (field.value !== id) {
                          setValue('model', '', { shouldDirty: true })
                          // The login belongs to the CLI: the new CLI starts with its default.
                          setValue('account_id', null, { shouldDirty: true })
                        }
                        field.onChange(id)
                      }}
                    >
                      <CliTag cli={id} label={t(`cli.${id}`)} size={28} />
                      <span className="min-w-0">
                        <span className="block font-medium">{t(`cli.${id}`)}</span>
                        <span className="block text-xs text-muted-foreground">
                          {detected && !detected.installed
                            ? t('cli.notDetected')
                            : `${t(`cli.vendor.${id}`)}${detected?.version ? ` · ${detected.version}` : ''}`}
                        </span>
                      </span>
                    </OptionCard>
                  )
                })}
              </div>
            )}
          />
        </Field>
        <Field
          label={t('agents.fields.model')}
          htmlFor="agent-model"
          error={
            info?.models_error ? t('cli.modelsError', { error: info.models_error }) : undefined
          }
        >
          <div className="flex gap-2">
            <Controller
              control={control}
              name="model"
              render={({ field }) => {
                const models = info?.models ?? []
                const known = !field.value || models.some((m) => m.id === field.value)
                return (
                  <Select
                    value={field.value || DEFAULT_MODEL}
                    onValueChange={(v) => field.onChange(v === DEFAULT_MODEL ? '' : v)}
                    disabled={isPending}
                  >
                    <SelectTrigger id="agent-model" className="w-full font-mono text-[12.5px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={DEFAULT_MODEL}>{t('cli.defaultModel')}</SelectItem>
                      {!known && <SelectItem value={field.value}>{field.value}</SelectItem>}
                      {models.map((m) => (
                        <SelectItem key={m.id} value={m.id}>
                          <span className="font-mono">{m.id}</span>
                          <span className="text-muted-foreground"> · {modelLabel(m)}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )
              }}
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label={t('cli.refresh')}
              title={t('cli.refresh')}
              disabled={refreshing}
              onClick={() => void onRefresh()}
            >
              <RefreshCw className={cn(refreshing && 'animate-spin')} />
            </Button>
          </div>
        </Field>
      </div>

      <Field
        label={t('agents.fields.account')}
        htmlFor="agent-account"
        help={t('agents.fields.accountHelp')}
        className="max-w-[512px]"
      >
        <Controller
          control={control}
          name="account_id"
          render={({ field }) => (
            <AccountSelect
              id="agent-account"
              cli={cli}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
      </Field>

      <FallbackWatch />

      <Field label={t('agents.fields.permissions')}>
        <Controller
          control={control}
          name="permission_mode"
          render={({ field }) => (
            <div
              role="radiogroup"
              aria-label={t('agents.fields.permissions')}
              className="grid grid-cols-3 gap-2"
            >
              {PERMISSION_MODES.map((mode) => {
                const Icon = PERMISSION_ICON[mode]
                return (
                  <OptionCard
                    key={mode}
                    selected={field.value === mode}
                    onSelect={() => field.onChange(mode)}
                  >
                    <Icon className="mt-0.5 size-4 shrink-0" />
                    <span>
                      <span className="block font-medium">{t(`agents.permission.${mode}`)}</span>
                      <span className="block text-xs text-pretty text-muted-foreground">
                        {t(`agents.permission.${mode}Help`)}
                      </span>
                    </span>
                  </OptionCard>
                )
              })}
            </div>
          )}
        />
      </Field>

      <Field label={t('agents.fields.tools')}>
        <Controller
          control={control}
          name="allowed_tools"
          render={({ field }) => (
            <div
              role="group"
              aria-label={t('agents.fields.tools')}
              className="flex flex-wrap gap-2"
            >
              {TOOLS.map((tool) => {
                const on = field.value.includes(tool)
                return (
                  <button
                    key={tool}
                    type="button"
                    role="checkbox"
                    aria-checked={on}
                    onClick={() =>
                      field.onChange(
                        on ? field.value.filter((x) => x !== tool) : [...field.value, tool],
                      )
                    }
                    className={cn(
                      'inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[12.5px]',
                      on
                        ? 'border-ring bg-accent font-medium'
                        : 'text-muted-foreground hover:border-ring',
                    )}
                  >
                    {on ? <Check className="size-3.5" /> : <Plus className="size-3.5" />}
                    {t(`agents.tool.${tool}`)}
                  </button>
                )
              })}
            </div>
          )}
        />
      </Field>

      <div className="grid grid-cols-3 gap-3">
        <Controller
          control={control}
          name="max_concurrency"
          render={({ field }) => (
            <div className="flex items-center justify-between rounded-lg border bg-card p-3.5">
              <div>
                <div className="font-medium">{t('agents.fields.concurrency')}</div>
                <div className="text-xs text-muted-foreground">
                  {t('agents.fields.concurrencyHelp')}
                </div>
              </div>
              <div className="flex items-center overflow-hidden rounded-md border">
                <button
                  type="button"
                  aria-label={t('agents.fields.decrease')}
                  disabled={field.value <= 1}
                  onClick={() => field.onChange(field.value - 1)}
                  className="grid size-8 place-items-center hover:bg-accent disabled:opacity-40"
                >
                  <Minus className="size-3.5" />
                </button>
                <output
                  aria-label={t('agents.fields.concurrency')}
                  className="w-8 text-center font-mono"
                >
                  {field.value}
                </output>
                <button
                  type="button"
                  aria-label={t('agents.fields.increase')}
                  disabled={field.value >= MAX_CONCURRENCY}
                  onClick={() => field.onChange(field.value + 1)}
                  className="grid size-8 place-items-center hover:bg-accent disabled:opacity-40"
                >
                  <Plus className="size-3.5" />
                </button>
              </div>
            </div>
          )}
        />
        {(
          [
            ['can_spawn_subagents', 'spawn'],
            ['can_create_tasks', 'createTasks'],
          ] as const
        ).map(([name, key]) => (
          <Controller
            key={name}
            control={control}
            name={name}
            render={({ field }) => (
              <div className="flex items-center justify-between gap-3 rounded-lg border bg-card p-3.5">
                <span>
                  <span id={`agent-${key}`} className="block font-medium">
                    {t(`agents.fields.${key}`)}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {t(`agents.fields.${key}Help`)}
                  </span>
                </span>
                <Switch
                  aria-labelledby={`agent-${key}`}
                  checked={field.value}
                  onCheckedChange={field.onChange}
                />
              </div>
            )}
          />
        ))}
      </div>
    </div>
  )
}
