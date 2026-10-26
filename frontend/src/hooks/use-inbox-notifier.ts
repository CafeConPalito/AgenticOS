import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { markNotified, useInboxSummary, useNotificationSettings } from '@/api/inbox'
import type { InboxKind, NotificationSettings } from '@/api/types'
import { notify } from '@/lib/notify'

/** Which setting covers each kind (same mapping as the backend). */
const SETTING: Record<InboxKind, keyof NotificationSettings> = {
  approval: 'approval',
  question: 'question',
  blocker: 'question',
  review: 'review',
  stalled: 'stalled',
  attention: 'stalled',
  delivery: 'delivery',
  limit: 'limits',
  quota: 'limits',
  account: 'limits',
  switch: 'limits',
  knowledge: 'review',
  skill: 'review',
  connection: 'limits',
  proposal: 'review',
}

/**
 * Notifies each new Inbox item once (ADR 0010): the backend keeps `notified_at`, so two windows
 * (or a reload) never notify the same item twice. Items of a disabled kind are only marked.
 */
export function useInboxNotifier() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const summary = useInboxSummary().data
  const settings = useNotificationSettings().data
  const handled = useRef(new Set<string>())

  useEffect(() => {
    // Never break the app over the notifier (e.g. an older backend without the Inbox).
    if (!summary || !settings || !Array.isArray(summary.unnotified)) return
    for (const item of summary.unnotified) {
      if (handled.current.has(item.id)) continue
      handled.current.add(item.id)
      void (async () => {
        if (settings[SETTING[item.kind]]) {
          const where = [item.agent_name, item.project_name].filter(Boolean).join(' · ')
          // Only an approval's command is meant for the person (limit and quota keep the CLI).
          const command = item.kind === 'approval' ? item.command : null
          const body = command ? `${item.title}\n${command}` : item.title
          await notify(`${t(`inbox.kinds.${item.kind}`)} · ${where}`, body, {
            sound: settings.sound,
            onClick: () => navigate(`/inbox?item=${item.id}`),
          })
        }
        await markNotified(item.id).catch(() => handled.current.delete(item.id))
      })()
    }
  }, [summary, settings, t, navigate])
}
