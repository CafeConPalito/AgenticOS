import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { Params } from 'react-router'
import { useAgent } from '@/api/agents'
import { useProject } from '@/api/projects'

/** Route `handle`: how a route contributes to the header breadcrumb. */
export interface CrumbHandle {
  crumb: (params: Params) => ReactNode
}

export function TextCrumb({
  i18nKey,
}: {
  i18nKey: 'nav.agents' | 'nav.projects' | 'agents.new.title' | 'projects.new.title'
}) {
  const { t } = useTranslation()
  return <>{t(i18nKey)}</>
}

export function AgentCrumb({ id }: { id?: string }) {
  const { data } = useAgent(id)
  if (!data) return <>…</>
  return (
    <>
      {data.name}
      {data.role ? ` · ${data.role}` : ''}
    </>
  )
}

export function ProjectCrumb({ id }: { id?: string }) {
  const { data } = useProject(id)
  return <>{data?.name ?? '…'}</>
}
