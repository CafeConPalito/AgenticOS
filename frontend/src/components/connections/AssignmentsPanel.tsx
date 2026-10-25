import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { KnowledgeLevel } from '@/api/knowledge'
import { type Connection, useAddAssignment, useRemoveAssignment } from '@/api/connections'
import { LevelSelect } from '@/components/skills/shared'
import { Button } from '@/components/ui/button'
import { connectionError, useLevelName } from './shared'

/** Where a connection is given: every agent, a project or one agent. */
export function AssignmentsPanel({ connection }: { connection: Connection }) {
  const { t } = useTranslation()
  const add = useAddAssignment()
  const remove = useRemoveAssignment()
  const levelName = useLevelName()
  const [level, setLevel] = useState<KnowledgeLevel>({ scope: 'general' })
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setError(null)
    try {
      await add.mutateAsync({ id: connection.id, level })
    } catch (failed) {
      setError(connectionError(failed))
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
      <p className="text-[12.5px] text-muted-foreground">{t('connections.assign.hint')}</p>
      {connection.assignments.length === 0 ? (
        <p className="text-[13px]">{t('connections.assign.none')}</p>
      ) : (
        <ul className="grid gap-2">
          {connection.assignments.map((assignment) => (
            <li
              key={assignment.id}
              className="flex items-center gap-2 rounded-lg border px-3 py-2 text-[13px]"
            >
              <span className="flex-1">{levelName(assignment)}</span>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-label={t('connections.assign.remove', { name: levelName(assignment) })}
                onClick={() => remove.mutate({ id: connection.id, assignmentId: assignment.id })}
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <LevelSelect value={level} onChange={setLevel} label={t('connections.assign.levelLabel')} />
        <Button type="button" size="sm" onClick={submit} disabled={add.isPending}>
          {t('connections.assign.add')}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-[13px] text-status-failed">
          {error}
        </p>
      )}
    </div>
  )
}
