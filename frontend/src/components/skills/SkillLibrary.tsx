import { Compass, Download, Plus, Puzzle } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { KnowledgeLevel } from '@/api/knowledge'
import { type Skill, useProposals, useSkillOrigin, useSkills } from '@/api/skills'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { SkillCard } from './SkillCard'
import { SkillEditor } from './SkillEditor'
import { SkillImportDialog } from './SkillImportDialog'
import { SkillProposalReview } from './SkillProposalReview'
import { SkillSheet } from './SkillSheet'
import { SkillTester } from './SkillTester'

/** A card that knows whether its registry has news (only installed skills ask). */
function LibraryCard({ skill, onOpen }: { skill: Skill; onOpen: (id: string) => void }) {
  const origin = useSkillOrigin(skill.id, skill.origin === 'registry')
  return <SkillCard skill={skill} onOpen={onOpen} update={origin.data?.update_available} />
}

const atLevel = (skill: Skill, level: KnowledgeLevel) =>
  skill.scope === level.scope &&
  (level.scope !== 'project' || skill.project_id === level.projectId) &&
  (level.scope !== 'agent' || skill.agent_id === level.agentId)

/**
 * The skills of one level (`docs/design/screens.md` §10): the cards with their switch and usage,
 * the agents' proposals waiting for review, creating and importing, and the tester.
 */
export function SkillLibrary({
  level,
  explore = false,
}: {
  level: KnowledgeLevel
  /** Shows the link to the registry explorer (the general page has it as a tab). */
  explore?: boolean
}) {
  const { t } = useTranslation()
  const skills = useSkills(level)
  const proposals = useProposals()
  const [opened, setOpened] = useState<string | null>(null)
  const [reviewing, setReviewing] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [importing, setImporting] = useState(false)
  const all = skills.data ?? []
  const approved = all.filter((s) => s.review === 'none')
  const active = approved.filter((s) => s.enabled).length
  const waiting = (proposals.data ?? []).filter((p) => atLevel(p.skill, level))

  return (
    <div className="flex flex-col gap-4 px-6 pt-5 pb-8">
      <p className="max-w-[760px] text-[13px] text-muted-foreground">
        {t(`skills.intro.${level.scope}`)}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" onClick={() => setCreating(true)}>
          <Plus />
          {t('skills.actions.new')}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => setImporting(true)}>
          <Download />
          {t('skills.actions.import')}
        </Button>
        {explore && (
          <Button asChild size="sm" variant="outline">
            <Link to="/conocimiento?vista=explorar">
              <Compass />
              {t('skills.actions.explore')}
            </Link>
          </Button>
        )}
        {approved.length > 0 && (
          <span className="ml-auto text-[12.5px] text-muted-foreground">
            {t('skills.count', { active, total: approved.length })}
          </span>
        )}
      </div>
      {waiting.length > 0 && (
        <section aria-label={t('skills.proposal.list', { count: waiting.length })}>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
            {waiting.map((proposal) => (
              <div key={proposal.version.id} className="flex flex-col gap-1">
                <SkillCard
                  skill={{ ...proposal.skill, review: 'proposed' }}
                  proposedBy={proposal.version.author.label}
                  onOpen={() => setReviewing(proposal.version.id)}
                />
              </div>
            ))}
          </div>
        </section>
      )}
      {skills.isPending ? (
        <Skeleton aria-busy className="h-24 rounded-lg" />
      ) : skills.isError ? (
        <p role="alert" className="text-status-failed">
          {t('skills.loadFailed')}
        </p>
      ) : approved.length === 0 ? (
        <EmptyState
          icon={Puzzle}
          title={t('skills.empty.title')}
          description={t('skills.empty.description')}
        />
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
          {approved.map((skill) => (
            <LibraryCard key={skill.id} skill={skill} onOpen={setOpened} />
          ))}
        </div>
      )}
      {approved.length > 0 && <SkillTester projectId={level.projectId} agentId={level.agentId} />}
      <SkillSheet skillId={opened} onClose={() => setOpened(null)} />
      <SkillProposalReview versionId={reviewing} onClose={() => setReviewing(null)} />
      {creating && <SkillEditor open onClose={() => setCreating(false)} level={level} />}
      <SkillImportDialog open={importing} onClose={() => setImporting(false)} level={level} />
    </div>
  )
}
