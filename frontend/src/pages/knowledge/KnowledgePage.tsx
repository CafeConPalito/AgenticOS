import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { KnowledgeLibrary } from '@/components/knowledge/KnowledgeLibrary'
import { RegistryExplorer } from '@/components/skills/registry/RegistryExplorer'
import { SkillLibrary } from '@/components/skills/SkillLibrary'
import { SkillStats } from '@/components/skills/stats/SkillStats'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const VIEWS = { docs: 'documentos', skills: 'skills', explore: 'explorar', usage: 'uso' } as const
type View = keyof typeof VIEWS

/** «Conocimiento y skills»: the general library, the skills, the public registries and the
 * skills' usage. The view is in the URL (`?vista=`), so it can be linked. */
export default function KnowledgePage() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const view =
    (Object.keys(VIEWS) as View[]).find((v) => VIEWS[v] === params.get('vista')) ?? 'docs'
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col">
      <header className="px-6 pt-[22px]">
        <h1 className="text-[22px] leading-[1.3] font-medium tracking-[-0.01em]">
          {t('nav.knowledge')}
        </h1>
      </header>
      <Tabs
        value={view}
        onValueChange={(next) => {
          const updated = new URLSearchParams(params)
          if (next === 'docs') updated.delete('vista')
          else updated.set('vista', VIEWS[next as View])
          setParams(updated, { replace: true })
        }}
        className="mt-3 gap-0"
      >
        <TabsList className="mx-6">
          {(Object.keys(VIEWS) as View[]).map((v) => (
            <TabsTrigger key={v} value={v}>
              {t(`skills.pageTabs.${v}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="docs">
          <KnowledgeLibrary level={{ scope: 'general' }} />
        </TabsContent>
        <TabsContent value="skills">
          <SkillLibrary level={{ scope: 'general' }} />
        </TabsContent>
        <TabsContent value="explore">
          <RegistryExplorer />
        </TabsContent>
        <TabsContent value="usage">
          <SkillStats />
        </TabsContent>
      </Tabs>
    </div>
  )
}
