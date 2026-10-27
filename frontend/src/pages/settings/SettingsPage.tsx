import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'
import { PageContainer, PageHeader } from '@/components/page'
import { cn } from '@/lib/utils'
import { AboutSection } from './AboutSection'
import { ArchitectSection } from './ArchitectSection'
import { CleanupSection } from './CleanupSection'
import { DictationSection } from './DictationSection'
import { GeneralSection } from './GeneralSection'
import { GitSection } from './GitSection'
import { KnowledgeSection } from './KnowledgeSection'
import { LimitsSection } from './LimitsSection'
import { LocalModelsSection } from './LocalModelsSection'
import { NotificationsSection } from './NotificationsSection'
import { ConnectionsSection } from './ConnectionsSection'
import { SkillsSection } from './SkillsSection'

/** The index groups (phase 20) and their sections, in order; each one is `/ajustes#<id>`. */
export const SECTION_GROUPS = [
  { id: 'app', sections: ['general', 'notifications', 'dictation', 'about'] },
  { id: 'agents', sections: ['limits', 'architect', 'git'] },
  { id: 'resources', sections: ['knowledge', 'skills', 'connections', 'models'] },
  { id: 'maintenance', sections: ['cleanup'] },
] as const

/** The sections, in the order of the groups. */
export const SECTIONS = SECTION_GROUPS.flatMap((group) => group.sections)
type SectionId = (typeof SECTIONS)[number]

const SECTION_BODY: Record<SectionId, () => React.ReactNode> = {
  general: GeneralSection,
  notifications: NotificationsSection,
  dictation: DictationSection,
  about: AboutSection,
  limits: LimitsSection,
  architect: ArchitectSection,
  git: GitSection,
  knowledge: KnowledgeSection,
  skills: SkillsSection,
  connections: ConnectionsSection,
  models: LocalModelsSection,
  cleanup: CleanupSection,
}

/** The id of the section that shows at the top of the scroll area. */
function useVisibleSection(): [SectionId, (id: SectionId) => void] {
  const [visible, setVisible] = useState<SectionId>(SECTIONS[0])
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return
    const seen = new Map<string, boolean>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) seen.set(entry.target.id, entry.isIntersecting)
        const first = SECTIONS.find((id) => seen.get(id))
        if (first) setVisible(first)
      },
      // The band just under the header counts as «the top».
      { rootMargin: '-72px 0px -60% 0px' },
    )
    for (const id of SECTIONS) {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [])
  return [visible, setVisible]
}

/** Ajustes: an index on the left and the sections on the right. */
export default function SettingsPage() {
  const { t } = useTranslation()
  const { hash } = useLocation()
  const navigate = useNavigate()
  const [visible, setVisible] = useVisibleSection()
  // The index scrolls smoothly by itself: the hash effect below must not jump over it.
  const fromIndex = useRef(false)

  // `/ajustes#clis` (from Inicio, the CLI notices…) scrolls to its section.
  useEffect(() => {
    const id = hash.slice(1)
    if (!id) return
    // The CLIs moved out of Ajustes (phase 10): old links to `#clis` land on their page.
    if (id === 'clis') {
      void navigate('/clis', { replace: true })
      return
    }
    if (fromIndex.current) {
      fromIndex.current = false
      return
    }
    document.getElementById(id)?.scrollIntoView({ block: 'start' })
    if ((SECTIONS as readonly string[]).includes(id)) setVisible(id as SectionId)
  }, [hash, setVisible, navigate])

  function go(id: SectionId) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    // Through the router, so `location.hash` follows and a later link to a section scrolls.
    if (hash !== `#${id}`) {
      fromIndex.current = true
      void navigate({ hash: id }, { replace: true })
    }
    setVisible(id)
  }

  return (
    <PageContainer>
      <PageHeader title={t('settings.title')} subtitle={t('settings.subtitle')} />
      <div className="grid grid-cols-[180px_minmax(0,1fr)] items-start gap-8 max-lg:grid-cols-1">
        <nav
          aria-label={t('settings.index')}
          className="sticky top-4 flex flex-col gap-0.5 max-lg:static max-lg:flex-row max-lg:flex-wrap"
        >
          {SECTION_GROUPS.map((group) => (
            <div key={group.id} className="flex flex-col gap-0.5 max-lg:contents">
              <p className="mt-3 mb-1 px-3 font-mono text-[10.5px] tracking-[0.12em] text-muted-foreground uppercase first:mt-0 max-lg:hidden">
                {t(`settings.groups.${group.id}`)}
              </p>
              {group.sections.map((id) => (
                <a
                  key={id}
                  href={`#${id}`}
                  aria-current={visible === id ? 'true' : undefined}
                  onClick={(e) => {
                    e.preventDefault()
                    go(id)
                  }}
                  className={cn(
                    'rounded-full px-3 py-1.5 text-[13px] text-muted-foreground hover:bg-accent hover:text-foreground',
                    visible === id && 'bg-accent font-medium text-foreground',
                  )}
                >
                  {t(`settings.sections.${id}`)}
                </a>
              ))}
            </div>
          ))}
        </nav>
        <div className="mx-auto flex w-full max-w-[1000px] flex-col gap-5">
          {SECTIONS.map((id) => {
            const Body = SECTION_BODY[id]
            return (
              <div key={id} id={id} className="scroll-mt-4">
                <Body />
              </div>
            )
          })}
        </div>
      </div>
    </PageContainer>
  )
}
