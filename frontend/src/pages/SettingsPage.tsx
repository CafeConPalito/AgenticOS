import { Bell, Gauge } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useNotificationSettings, useSaveNotificationSettings } from '@/api/inbox'
import type { NotificationSettings, UsageLimits } from '@/api/types'
import { PageContainer, PageHeader } from '@/components/page'
import { useSaveUsageLimits, useUsageLimits } from '@/api/usage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/form-errors'
import {
  askNotificationPermission,
  notificationPermission,
  notify,
  type NotifyPermission,
} from '@/lib/notify'

const KEYS: (keyof NotificationSettings)[] = [
  'approval',
  'question',
  'review',
  'stalled',
  'delivery',
  'limits',
  'sound',
]

export default function SettingsPage() {
  const { t } = useTranslation()
  const settings = useNotificationSettings().data
  const save = useSaveNotificationSettings()
  const [permission, setPermission] = useState<NotifyPermission | null>(null)

  useEffect(() => {
    void notificationPermission().then(setPermission)
  }, [])

  function toggle(key: keyof NotificationSettings, value: boolean) {
    if (!settings) return
    save.mutate({ ...settings, [key]: value }, { onError: (e) => toast.error(errorMessage(e)) })
  }

  return (
    <PageContainer narrow>
      <PageHeader title={t('settings.title')} subtitle={t('settings.subtitle')} />
      <section
        aria-labelledby="notifications-title"
        className="flex flex-col gap-1 rounded-xl border bg-card p-4"
      >
        <h2 id="notifications-title" className="flex items-center gap-2 text-[15px] font-medium">
          <Bell className="size-4" />
          {t('settings.notifications.title')}
        </h2>
        <p className="mb-2 text-[13px] text-muted-foreground">
          {t('settings.notifications.description')}
        </p>
        {permission && permission !== 'granted' && (
          <div className="mb-2 flex items-center gap-3 rounded-lg border border-status-waiting/40 bg-status-waiting/10 px-3 py-2 text-[13px]">
            <span className="flex-1">{t('settings.notifications.permissionDenied')}</span>
            {permission === 'default' && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => void askNotificationPermission().then(setPermission)}
              >
                {t('settings.notifications.askPermission')}
              </Button>
            )}
          </div>
        )}
        {KEYS.map((key) => (
          <label
            key={key}
            className="flex items-center gap-4 border-b py-2.5 last:border-b-0"
            htmlFor={`notify-${key}`}
          >
            <span className="flex-1">
              <span className="block text-[13.5px] font-medium">
                {t(`settings.notifications.${key}`)}
              </span>
              <span className="block text-xs text-muted-foreground">
                {t(`settings.notifications.${key}Help`)}
              </span>
            </span>
            <Switch
              id={`notify-${key}`}
              checked={settings?.[key] ?? false}
              disabled={!settings || save.isPending}
              onCheckedChange={(value) => toggle(key, value)}
            />
          </label>
        ))}
        <div className="pt-2">
          <Button
            size="sm"
            variant="outline"
            disabled={permission !== 'granted'}
            onClick={() =>
              void notify(
                t('settings.notifications.testTitle'),
                t('settings.notifications.testBody'),
                {
                  sound: settings?.sound ?? true,
                },
              )
            }
          >
            {t('settings.notifications.test')}
          </Button>
        </div>
      </section>
      <LimitsSection />
    </PageContainer>
  )
}

/** «Límites diarios» (phase 07): USD for Claude Code, tokens for Antigravity. */
function LimitsSection() {
  const limits = useUsageLimits().data
  return limits ? <LimitsForm initial={limits} /> : <Skeleton className="h-48 rounded-xl" />
}

function LimitsForm({ initial }: { initial: UsageLimits }) {
  const { t } = useTranslation()
  const save = useSaveUsageLimits()
  const [claude, setClaude] = useState(
    initial.claude_usd === null ? '' : String(initial.claude_usd),
  )
  const [agy, setAgy] = useState(initial.agy_tokens === null ? '' : String(initial.agy_tokens))

  const parse = (text: string, integer: boolean): number | null | undefined => {
    const clean = text.trim().replace(/\s/g, '').replace(',', '.')
    if (!clean) return null
    const value = integer ? Number(clean.replace(/\./g, '')) : Number(clean)
    return Number.isFinite(value) && value > 0 ? value : undefined
  }
  const claudeValue = parse(claude, false)
  const agyValue = parse(agy, true)
  const invalid = claudeValue === undefined || agyValue === undefined

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (invalid) return
    save.mutate(
      { claude_usd: claudeValue, agy_tokens: agyValue === null ? null : Math.round(agyValue) },
      {
        onSuccess: () => toast.success(t('settings.limits.saved')),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  return (
    <section
      aria-labelledby="limits-title"
      className="flex flex-col gap-1 rounded-xl border bg-card p-4"
    >
      <h2 id="limits-title" className="flex items-center gap-2 text-[15px] font-medium">
        <Gauge className="size-4" />
        {t('settings.limits.title')}
      </h2>
      <p className="mb-2 text-[13px] text-muted-foreground">{t('settings.limits.description')}</p>
      <form onSubmit={submit} className="flex flex-col">
        {(
          [
            ['claude', claude, setClaude, '$'],
            ['agy', agy, setAgy, 'tokens'],
          ] as const
        ).map(([key, value, setValue, unit]) => (
          <label
            key={key}
            htmlFor={`limit-${key}`}
            className="flex items-center gap-4 border-b py-2.5 last:border-b-0"
          >
            <span className="flex-1">
              <span className="block text-[13.5px] font-medium">{t(`settings.limits.${key}`)}</span>
              <span className="block text-xs text-muted-foreground">
                {t(`settings.limits.${key}Help`)}
              </span>
            </span>
            <span className="flex items-center gap-2">
              <Input
                id={`limit-${key}`}
                inputMode="decimal"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={t('settings.limits.none')}
                className="h-8 w-[140px] text-right font-mono"
              />
              <span className="w-12 text-xs text-muted-foreground">{unit}</span>
            </span>
          </label>
        ))}
        {invalid && (
          <p role="alert" className="pt-2 text-[12.5px] text-status-failed">
            {t('settings.limits.invalid')}
          </p>
        )}
        <div className="pt-3">
          <Button
            type="submit"
            size="sm"
            disabled={invalid || save.isPending}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('settings.limits.save')}
          </Button>
        </div>
      </form>
    </section>
  )
}
