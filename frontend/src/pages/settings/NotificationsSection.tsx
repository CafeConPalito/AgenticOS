import { Bell } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useNotificationSettings, useSaveNotificationSettings } from '@/api/inbox'
import type { NotificationSettings } from '@/api/types'
import { Button } from '@/components/ui/button'
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

/** «Notificaciones de Windows»: which Inbox kinds notify, and the sound. */
export function NotificationsSection() {
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
  )
}
