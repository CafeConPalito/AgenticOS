import { useTranslation } from 'react-i18next'
import type { Run } from '@/api/types'
import { StatusBadge, type StatusTone } from '@/components/agentic/primitives'
import type es from '@/i18n/es.json'

type RunLike = Pick<Run, 'status' | 'activity' | 'exit_code'>
type StatusKey = keyof typeof es.runs.status

function toneAndLabel(run: RunLike): { tone: StatusTone; key: StatusKey; live: boolean } {
  switch (run.status) {
    case 'starting':
      return { tone: 'queued', key: 'starting', live: true }
    case 'running':
      return run.activity === 'busy'
        ? { tone: 'running', key: 'busy', live: true }
        : { tone: 'running', key: 'idle', live: false }
    case 'intervening':
      return { tone: 'waiting', key: 'intervening', live: false }
    case 'exited':
      return { tone: run.exit_code ? 'failed' : 'done', key: 'exited', live: false }
    case 'failed':
      return { tone: 'failed', key: 'failed', live: false }
    default: // stopped, interrupted
      return { tone: 'cancelled', key: run.status, live: false }
  }
}

/** Run status with a pulsing dot while the agent is working. */
export function RunStatusBadge({ run, size = 'sm' }: { run: RunLike; size?: 'md' | 'sm' | 'xs' }) {
  const { t } = useTranslation()
  const { tone, key, live } = toneAndLabel(run)
  return <StatusBadge tone={tone} label={t(`runs.status.${key}`)} size={size} live={live} />
}
