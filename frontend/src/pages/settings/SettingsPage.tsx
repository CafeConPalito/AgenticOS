import { AppWindow, Bot, Library, Wrench, type LucideIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'
import { PageContainer, PageHeader } from '@/components/page'
import { cn } from '@/lib/utils'
import { AboutSection } from './AboutSection'
import { AppearanceSection } from './AppearanceSection'
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
  { id: 'app', sections: ['general', 'appearance', 'notifications', 'dictation', 'about'] },
  { id: 'agents', sections: ['limits', 'architect', 'git'] },
  { id: 'resources', sections: ['knowledge', 'skills', 'connections', 'models'] },
  { id: 'maintenance', sections: ['cleanup'] },
] as const

/** The icon of each group's title in the index (phase 22). */
const GROUP_ICONS: Record<(typeof SECTION_GROUPS)[number]['id'], LucideIcon> = {
  app: AppWindow,
  agents: Bot,
  resources: Library,
  maintenance: Wrench,
}

/** The sections, in the order of the groups. */
export const SECTIONS = SECTION_GROUPS.flatMap((group) => group.sections)
type SectionId = (typeof SECTIONS)[number]

const SECTION_BODY: Record<SectionId, () => React.ReactNode> = {
  general: GeneralSection,
  appearance: AppearanceSection,
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
          className="sticky top-4 flex flex-col max-lg:static max-lg:gap-2"
        >
          {SECTION_GROUPS.map((group) => {
            const Icon = GROUP_ICONS[group.id]
            return (
              // Titles stand apart from the sections (phase 22): stronger, with an icon and a
              // rule between groups; on narrow screens each group is a row led by its title.
              <div
                key={group.id}
                role="group"
                aria-labelledby={`settings-group-${group.id}`}
                className="flex flex-col gap-0.5 border-sep not-first:mt-3 not-first:border-t not-first:pt-3 max-lg:flex-row max-lg:flex-wrap max-lg:items-center max-lg:gap-1 max-lg:not-first:mt-0 max-lg:not-first:pt-2"
              >
                <p
                  id={`settings-group-${group.id}`}
                  className="mb-1 flex items-center gap-2 px-3 text-[12px] font-semibold tracking-wide text-foreground max-lg:mb-0 max-lg:w-full max-lg:px-1"
                >
                  <Icon className="size-3.5 text-muted-foreground" aria-hidden />
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
                      'rounded-full py-1.5 pr-3 pl-8 text-[13px] text-muted-foreground hover:bg-accent hover:text-foreground max-lg:px-3',
                      visible === id && 'bg-accent font-medium text-foreground',
                    )}
                  >
                    {t(`settings.sections.${id}`)}
                  </a>
                ))}
              </div>
            )
          })}
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
