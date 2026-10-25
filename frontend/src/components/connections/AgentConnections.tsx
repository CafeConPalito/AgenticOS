import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useAddAssignment,
  useAgentConnections,
  usePutAgentExclusions,
  useStageConnections,
  usePutStageExclusions,
} from '@/api/connections'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ReceivedConnections } from './ReceivedConnections'
import { connectionError } from './shared'

/** «Conexiones» tab of an agent: what it receives, taking one away, and giving it another. */
export function AgentConnections({ agentId }: { agentId: string }) {
  const { t } = useTranslation()
  const view = useAgentConnections(agentId)
  const put = usePutAgentExclusions(agentId)
  const add = useAddAssignment()
  const [pick, setPick] = useState('')

  async function give() {
    if (!pick) return
    try {
      await add.mutateAsync({ id: pick, level: { scope: 'agent', agentId } })
      setPick('')
    } catch (failed) {
      toast.error(connectionError(failed))
    }
  }

  return (
    <div className="flex flex-col gap-4 px-6 pt-5 pb-8">
      <p className="max-w-[760px] text-[13px] text-muted-foreground">
        {t('connections.agentTab.intro')}
      </p>
      {view.isPending ? (
        <Skeleton aria-busy className="h-24 rounded-lg" />
      ) : view.isError ? (
        <p role="alert" className="text-status-failed">
          {t('connections.loadFailed')}
        </p>
      ) : (
        <>
          <ReceivedConnections
            scope="agent"
            preview={view.data}
            excludedIds={view.data.excluded_ids}
            onChange={(excluded) => put.mutate(excluded)}
          />
          {view.data.available.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <Select value={pick} onValueChange={setPick}>
                <SelectTrigger
                  aria-label={t('connections.agentTab.pick')}
                  className="h-8 w-[240px]"
                >
                  <SelectValue placeholder={t('connections.agentTab.pickPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {view.data.available.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button type="button" size="sm" disabled={!pick || add.isPending} onClick={give}>
                {t('connections.agentTab.give')}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** The same for a pipeline stage (a branch is one): what it takes away from its agent's. */
export function StageConnections({ stageId }: { stageId: string }) {
  const { t } = useTranslation()
  const view = useStageConnections(stageId)
  const put = usePutStageExclusions(stageId)
  if (view.isPending) return <Skeleton aria-busy className="h-16 rounded-lg" />
  if (view.isError) return null
  return (
    <section className="grid gap-2" aria-label={t('connections.stageSection.title')}>
      <h3 className="text-[12.5px] text-muted-foreground">{t('connections.stageSection.title')}</h3>
      <p className="text-[12px] text-muted-foreground">{t('connections.stageSection.hint')}</p>
      <ReceivedConnections
        scope="stage"
        preview={view.data}
        excludedIds={view.data.excluded_ids}
        onChange={(excluded) => put.mutate(excluded)}
      />
    </section>
  )
}
