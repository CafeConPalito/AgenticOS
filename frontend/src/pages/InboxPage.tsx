import { Inbox } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { useInbox, useInboxSummary } from '@/api/inbox'
import { EmptyState } from '@/components/EmptyState'
import { PageContainer, PageHeader } from '@/components/page'
import { RequestItem } from '@/components/requests/RequestItem'
import { cn } from '@/lib/utils'

export default function InboxPage() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const view =
    params.get('status') === 'resolved' || params.get('vista') === 'resueltas'
      ? 'resolved'
      : 'pending'
  const items = useInbox(view)
  const summary = useInboxSummary().data
  const focused = params.get('item')

  useEffect(() => {
    if (focused) document.getElementById(`inbox-${focused}`)?.scrollIntoView({ block: 'center' })
  }, [focused, items.data])

  return (
    <PageContainer>
      <div className="mx-auto flex w-full max-w-[1080px] flex-col gap-5">
        <PageHeader
          title={t('inbox.title')}
          subtitle={t('inbox.subtitle')}
          actions={
            <div role="tablist" className="flex rounded-lg border bg-subtle p-0.5">
              {(['pending', 'resolved'] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  role="tab"
                  aria-selected={view === v}
                  onClick={() =>
                    setParams(v === 'pending' ? {} : { status: 'resolved' }, { replace: true })
                  }
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-[13px] text-muted-foreground',
                    view === v && 'bg-card font-medium text-foreground shadow-sm',
                  )}
                >
                  {t(`inbox.${v}`)}
                  <span className="font-mono text-[11px]">{summary?.[v] ?? ''}</span>
                </button>
              ))}
            </div>
          }
        />
        {items.data && items.data.length === 0 ? (
          view === 'pending' ? (
            <EmptyState
              icon={Inbox}
              title={t('inbox.emptyTitle')}
              description={t('inbox.emptyDescription')}
            />
          ) : (
            <p className="text-sm text-muted-foreground">{t('inbox.emptyResolved')}</p>
          )
        ) : (
          <ul className="flex flex-col gap-4">
            {(items.data ?? []).map((item) => (
              <li key={item.id} id={`inbox-${item.id}`}>
                <RequestItem item={item} focused={item.id === focused} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </PageContainer>
  )
}
