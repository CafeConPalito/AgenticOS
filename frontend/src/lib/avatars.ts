import { useEffect, useState } from 'react'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import { getApiBaseUrl } from '@/lib/api'

/** The owl gallery (phase 20): `assets/owls/<id>.svg`, drawn by `scripts/owls.py`. */
const OWL_URLS = import.meta.glob<string>('../assets/owls/*.svg', {
  eager: true,
  query: '?url',
  import: 'default',
})

export const OWLS: { id: string; url: string }[] = Object.entries(OWL_URLS)
  .map(([path, url]) => ({ id: path.replace(/^.*\/(.+)\.svg$/, '$1'), url }))
  // «plain» first, then by name.
  .sort((a, b) => Number(b.id === 'plain') - Number(a.id === 'plain') || a.id.localeCompare(b.id))

const OWL_BY_ID = new Map(OWLS.map((owl) => [owl.id, owl.url]))

let knownBase: string | null = null

/** The backend's base URL, known at once after the first time (photos are served by it). */
export function useApiBase(): string | null {
  const [base, setBase] = useState(knownBase)
  useEffect(() => {
    if (base) return
    let alive = true
    void getApiBaseUrl()
      .then((url) => {
        knownBase = url
        if (alive) setBase(url)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [base])
  return base
}

/** Where to load an avatar from: an owl's asset or a stored photo; null for the initials. */
export function avatarSource(
  avatar: string | null | undefined,
  base: string | null,
): string | null {
  if (!avatar) return null
  if (avatar.startsWith('owl:')) return OWL_BY_ID.get(avatar.slice(4)) ?? null
  const photo = /^photo:([0-9a-f]{12})$/.exec(avatar)
  return photo && base ? `${base}/api/avatars/${photo[1]}.webp` : null
}

/**
 * The avatar of an agent known only by its id (runs, tasks, the Inbox carry its name and
 * color, not its picture): read from the agents list the app already keeps.
 */
export function useAgentAvatar(agentId: string | null | undefined): string | null {
  const agents = useAgents({ enabled: Boolean(agentId) }).data
  return agentId ? (agents?.find((a) => a.id === agentId)?.avatar ?? null) : null
}

/**
 * Phase 24: the photo of a project known only by its id (tasks, runs and the Inbox carry its
 * name and color): read from the projects list the app already keeps.
 */
export function useProjectAvatar(projectId: string | null | undefined): string | null {
  const projects = useProjects().data
  return projectId ? (projects?.find((p) => p.id === projectId)?.avatar ?? null) : null
}
