import { useQuery } from '@tanstack/react-query'
import { Pause, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { knowledgeKeys, useQueue, useSetPaused, type SystemLoad } from '@/api/knowledge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'

function Meter({
  label,
  percent,
  appPercent,
  detail,
}: {
  label: string
  percent: number | null
  appPercent?: number
  detail?: string
}) {
  const { t } = useTranslation()
  return (
    <div className="flex min-w-[150px] flex-1 flex-col gap-1">
      <div className="flex items-baseline justify-between text-[12px]">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono tabular-nums">
          {percent === null ? t('knowledge.monitor.unavailable') : `${Math.round(percent)} %`}
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent === null ? undefined : Math.round(percent)}
        className="relative h-1.5 overflow-hidden rounded-full bg-muted"
      >
        {percent !== null && (
          <>
            <div
              className="absolute inset-y-0 left-0 bg-muted-foreground/40"
              style={{ width: `${percent}%` }}
            />
            <div
              className="absolute inset-y-0 left-0 bg-primary-action"
              style={{ width: `${Math.min(percent, appPercent ?? 0)}%` }}
            />
          </>
        )}
      </div>
      {detail && <span className="text-[11px] text-muted-foreground">{detail}</span>}
    </div>
  )
}

/**
 * CPU, GPU and memory of the machine while documents are processed, with the app's share in
 * the stronger colour, and the button that pauses the queue.
 */
export function ResourceMonitor() {
  const { t } = useTranslation()
  const queue = useQueue()
  const setPaused = useSetPaused()
  const busy = (queue.data?.active.length ?? 0) > 0
  const load = useQuery({
    queryKey: knowledgeKeys.system,
    queryFn: () => api.get<SystemLoad>('/api/knowledge/system'),
    enabled: busy,
    staleTime: Infinity, // live `system` events keep it fresh
  })
  const state = queue.data
  if (!state || (!busy && state.queued === 0 && !state.paused && !state.reindexing)) return null

  const data = load.data
  return (
    <section
      aria-label={t('knowledge.monitor.title')}
      className="flex flex-wrap items-center gap-4 rounded-lg border bg-subtle px-4 py-3"
    >
      <div className="min-w-[170px]">
        <div className="text-[13px] font-medium">
          {state.paused
            ? t('knowledge.monitor.paused')
            : state.reindexing
              ? t('knowledge.monitor.reindexing')
              : t('knowledge.monitor.working')}
        </div>
        <div className="text-[12px] text-muted-foreground">
          {t('knowledge.monitor.queue', { count: state.queued, active: state.active.length })}
        </div>
      </div>
      <Meter
        label={t('knowledge.monitor.cpu')}
        percent={data?.cpu.percent ?? null}
        appPercent={data?.cpu.app_percent}
        detail={
          data ? t('knowledge.monitor.app', { value: Math.round(data.cpu.app_percent) }) : undefined
        }
      />
      <Meter
        label={t('knowledge.monitor.gpu')}
        percent={data?.gpu?.percent ?? null}
        appPercent={data?.gpu?.app_percent}
        detail={
          data?.gpu
            ? t('knowledge.monitor.app', { value: Math.round(data.gpu.app_percent) })
            : undefined
        }
      />
      <Meter
        label={t('knowledge.monitor.memory')}
        percent={data?.memory.percent ?? null}
        appPercent={data ? (data.memory.app_mb / data.memory.total_mb) * 100 : undefined}
        detail={
          data
            ? t('knowledge.monitor.memoryDetail', {
                used: (data.memory.used_mb / 1024).toFixed(1),
                total: (data.memory.total_mb / 1024).toFixed(0),
                app: data.memory.app_mb,
              })
            : undefined
        }
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={setPaused.isPending}
        onClick={() => setPaused.mutate(!state.paused)}
      >
        {state.paused ? <Play /> : <Pause />}
        {state.paused ? t('knowledge.monitor.resume') : t('knowledge.monitor.pause')}
      </Button>
    </section>
  )
}
