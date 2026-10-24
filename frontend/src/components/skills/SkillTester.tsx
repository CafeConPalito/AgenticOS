import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import { type Skill, useTrySkills } from '@/api/skills'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'

const NONE = '-'

/** «Probar la selección»: which skills a run would get for a task, and why the rest not. */
export function SkillTester({
  projectId,
  agentId,
  stageId,
}: {
  projectId?: string
  agentId?: string
  stageId?: string
}) {
  const { t } = useTranslation()
  const agents = useAgents().data ?? []
  const run = useTrySkills()
  const [text, setText] = useState('')
  const [agent, setAgent] = useState(agentId ?? NONE)
  const result = run.data

  function submit(event: React.FormEvent) {
    event.preventDefault()
    run.mutate(
      {
        text,
        agent_id: agent === NONE ? null : agent,
        project_id: projectId ?? null,
        stage_id: stageId ?? null,
      },
      { onError: (error) => toast.error(errorMessage(error)) },
    )
  }

  const name = (skill: Skill) => <span className="font-mono">{skill.name}</span>

  return (
    <section
      aria-label={t('skills.tester.title')}
      className="flex flex-col gap-3 rounded-xl border border-sep p-4"
    >
      <div>
        <h3 className="text-[14px] font-medium">{t('skills.tester.title')}</h3>
        <p className="text-[12.5px] text-muted-foreground">{t('skills.tester.hint')}</p>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-2">
        <Label htmlFor="skill-try-text">{t('skills.tester.text')}</Label>
        <Textarea
          id="skill-try-text"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="flex items-center gap-2">
          {!agentId && (
            <Select value={agent} onValueChange={setAgent}>
              <SelectTrigger aria-label={t('skills.tester.agent')} className="h-8 w-[200px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{t('skills.tester.any')}</SelectItem>
                {agents.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button type="submit" size="sm" disabled={!text.trim() || run.isPending}>
            {t('skills.tester.run')}
          </Button>
        </div>
      </form>
      {result && (
        <div className="flex flex-col gap-2 text-[13px]">
          <p className="text-[12px] text-muted-foreground">
            {t(`skills.tester.method.${result.method}`)}
          </p>
          {result.always.length > 0 && (
            <div>
              <h4 className="font-medium">{t('skills.tester.always')}</h4>
              <ul className="ml-4 list-disc">
                {result.always.map((skill) => (
                  <li key={skill.id}>{name(skill)}</li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <h4 className="font-medium">{t('skills.tester.candidates')}</h4>
            <ol aria-label={t('skills.tester.candidates')} className="ml-4 list-decimal">
              {result.candidates.map(({ skill, score }) => (
                <li key={skill.id}>
                  {name(skill)}
                  {score !== null && (
                    <span className="text-muted-foreground">
                      {' '}
                      · {t('skills.tester.score', { score: score.toFixed(2) })}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </div>
          {result.excluded.length > 0 && (
            <div>
              <h4 className="font-medium">{t('skills.tester.excluded')}</h4>
              <ul className="ml-4 list-disc text-muted-foreground">
                {result.excluded.map(({ skill, reason }) => (
                  <li key={skill.id}>
                    {name(skill)} — {t(`skills.tester.reason.${reason}`)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <details>
            <summary className="cursor-pointer">{t('skills.tester.section')}</summary>
            <pre className="mt-2 max-h-[300px] overflow-auto rounded bg-subtle p-2 font-mono text-[12px] whitespace-pre-wrap">
              {result.section}
            </pre>
          </details>
        </div>
      )}
    </section>
  )
}
