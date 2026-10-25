import { useTranslation } from 'react-i18next'
import type { ConnectionAssignment, TestError } from '@/api/connections'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import { ApiError } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'

/** The `${secret:KEY}` / `${env:NAME}` placeholders of a text (`secret` ones are the secrets of
 * the connection; `env` ones come from the person's own environment). */
const PLACEHOLDER = /\$\{(secret|env):([A-Za-z0-9_.-]+)\}/g

export function secretKeysIn(...texts: string[]): string[] {
  const keys: string[] = []
  for (const text of texts) {
    for (const match of text.matchAll(PLACEHOLDER)) {
      if (match[1] === 'secret' && !keys.includes(match[2])) keys.push(match[2])
    }
  }
  return keys
}

/** A name for a secret made from a variable or header name: `X-Api-Key` → `X_API_KEY`. */
export function secretKeyFor(name: string): string {
  const key = name
    .replace(/[^A-Za-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toUpperCase()
  return key || 'SECRET'
}

export const placeholder = (key: string) => `\${secret:${key}}`

/**
 * The reason the backend gave, when it is one of its sentences about the connection (they are
 * already in Spanish: name taken, command missing, a secret that does not exist…); the generic
 * message for anything else.
 */
export function connectionError(error: unknown): string {
  if (error instanceof ApiError && [409, 422, 502, 503].includes(error.status)) {
    return error.message
  }
  return errorMessage(error)
}

/** What went wrong in a test, in words (the backend wrote them). */
export function TestErrorBox({ error }: { error: TestError }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-status-failed/40 bg-status-failed/5 p-3 text-[12.5px]"
    >
      <p className="whitespace-pre-wrap">{error.message}</p>
    </div>
  )
}

/** «Tienda», «Dev»… for an assignment (the ids alone mean nothing to the person). */
export function useLevelName() {
  const { t } = useTranslation()
  const projects = useProjects().data ?? []
  const agents = useAgents().data ?? []
  return (assignment: Pick<ConnectionAssignment, 'scope' | 'project_id' | 'agent_id'>) => {
    if (assignment.scope === 'project') {
      return t('connections.level.project_named', {
        name: projects.find((p) => p.id === assignment.project_id)?.name ?? '…',
      })
    }
    if (assignment.scope === 'agent') {
      return t('connections.level.agent_named', {
        name: agents.find((a) => a.id === assignment.agent_id)?.name ?? '…',
      })
    }
    return t('connections.level.general')
  }
}
