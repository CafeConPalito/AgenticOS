import { WifiOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'

export function OfflineBanner({ onRetry, url }: { onRetry: () => void; url?: string }) {
  const { t } = useTranslation()
  return (
    <div
      role="alert"
      className="flex shrink-0 items-center gap-2.5 border-b border-[color-mix(in_oklch,var(--status-failed)_40%,transparent)] bg-[color-mix(in_oklch,var(--status-failed)_14%,var(--background))] px-[18px] py-[9px] text-[12.5px]"
    >
      <WifiOff className="size-4 text-status-failed" />
      <strong className="font-medium">{t('backend.offlineTitle')}</strong>
      <span className="text-muted-foreground">{t('backend.offlineDescription')}</span>
      <Button size="sm" variant="outline" className="ml-auto h-[26px]" onClick={onRetry}>
        {t('backend.retry')}
      </Button>
      {url && <span className="font-mono text-xs text-muted-foreground">{url}</span>}
    </div>
  )
}
