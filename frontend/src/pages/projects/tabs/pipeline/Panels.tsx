import { Plus, Trash2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Agent, DeciderCli } from '@/api/types'
import { AgentAvatar } from '@/components/agentic/primitives'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { graphOf, linksFrom, newLink, type Draft, type DraftLink, type DraftStage } from './model'
import { rejectCandidates } from './validate'
import { StageConnections } from '@/components/connections/AgentConnections'
import { SkillModes } from '@/components/skills/SkillModes'

const NONE = '__none__'

interface PanelProps {
  draft: Draft
  onChange: (update: (draft: Draft) => Draft) => void
}

const patchStage = (key: string, values: Partial<DraftStage>) => (d: Draft) => ({
  ...d,
  stages: d.stages.map((s) => (s.key === key ? { ...s, ...values } : s)),
})

const patchLink = (key: string, values: Partial<DraftLink>) => (d: Draft) => ({
  ...d,
  links: d.links.map((l) => (l.key === key ? { ...l, ...values } : l)),
})

/** The editable fields of one stage and its links to the stages that follow. */
export function StagePanel({
  stage,
  draft,
  agents,
  onChange,
  onSelectLink,
  onRemove,
}: PanelProps & {
  stage: DraftStage
  agents: Agent[]
  onSelectLink: (key: string) => void
  onRemove: () => void
}) {
  const { t } = useTranslation()
  const index = draft.stages.findIndex((s) => s.key === stage.key)
  const nameOf = (key: string) => draft.stages.find((s) => s.key === key)?.name ?? ''
  const outs = linksFrom(draft, stage.key)
  const candidates = rejectCandidates(graphOf(draft), stage.key)
  const free = draft.stages.filter(
    (s) => s.key !== stage.key && !outs.some((l) => l.target === s.key),
  )
  const others = candidates.filter((k) => k !== stage.rejectTo)

  return (
    <section aria-label={t('pipeline.stagePanel', { name: stage.name })} className="grid gap-3">
      <Field label={t('pipeline.stageName', { n: index + 1 })}>
        <Input
          value={stage.name}
          maxLength={80}
          onChange={(e) => onChange(patchStage(stage.key, { name: e.target.value }))}
        />
      </Field>
      <Field label={t('pipeline.agent', { n: index + 1 })}>
        <Select
          value={stage.agentId ?? NONE}
          onValueChange={(v) => onChange(patchStage(stage.key, { agentId: v === NONE ? null : v }))}
        >
          <SelectTrigger className="h-10 w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>{t('pipeline.noAgent')}</SelectItem>
            {agents.map((a) => (
              <SelectItem key={a.id} value={a.id}>
                <AgentAvatar name={a.name} color={a.color} agentId={a.id} size={20} />
                <span>
                  {a.name}
                  {a.role && <span className="text-muted-foreground"> · {a.role}</span>}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <label className="flex items-center gap-2 text-[13px]">
        <Switch
          checked={stage.requiresReview}
          onCheckedChange={(v) => onChange(patchStage(stage.key, { requiresReview: v }))}
        />
        {t('pipeline.requiresReview')}
      </label>

      {candidates.length > 0 && (
        <Field label={t('pipeline.rejectTo')}>
          <Select
            value={stage.rejectTo ?? NONE}
            onValueChange={(v) =>
              onChange(
                patchStage(stage.key, {
                  rejectTo: v === NONE ? null : v,
                  rejectAlso: stage.rejectAlso.filter((k) => k !== v),
                }),
              )
            }
          >
            <SelectTrigger className="h-9 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t('pipeline.noReject')}</SelectItem>
              {candidates.map((k) => (
                <SelectItem key={k} value={k}>
                  {nameOf(k)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      )}
      {stage.rejectTo && others.length > 0 && (
        <fieldset className="grid gap-1.5">
          <legend className="mb-1 text-[12.5px] text-muted-foreground">
            {t('pipeline.rejectAlso')}
          </legend>
          {others.map((k) => (
            <label key={k} className="flex items-center gap-2 text-[13px]">
              <input
                type="checkbox"
                checked={stage.rejectAlso.includes(k)}
                onChange={(e) =>
                  onChange(
                    patchStage(stage.key, {
                      rejectAlso: e.target.checked
                        ? [...stage.rejectAlso, k]
                        : stage.rejectAlso.filter((x) => x !== k),
                    }),
                  )
                }
              />
              {nameOf(k)}
            </label>
          ))}
        </fieldset>
      )}

      {stage.id ? (
        <SkillModes stageId={stage.id} />
      ) : (
        <p className="text-[12.5px] text-muted-foreground">{t('skills.modes.saveFirst')}</p>
      )}
      {stage.id && <StageConnections stageId={stage.id} />}

      <div className="grid gap-1.5">
        <h3 className="text-[12.5px] text-muted-foreground">{t('pipeline.next')}</h3>
        {outs.length === 0 && <p className="text-[12.5px]">{t('pipeline.isFinal')}</p>}
        <ul className="grid gap-1">
          {outs.map((l) => (
            <li key={l.key} className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 min-w-0 flex-1 justify-start px-2 text-[13px]"
                onClick={() => onSelectLink(l.key)}
              >
                <span className="truncate">
                  {outs.length > 1 && l.name ? `${l.name} → ` : '→ '}
                  {nameOf(l.target)}
                </span>
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t('pipeline.removeLink', { to: nameOf(l.target) })}
                onClick={() =>
                  onChange((d) => ({ ...d, links: d.links.filter((x) => x.key !== l.key) }))
                }
              >
                <X />
              </Button>
            </li>
          ))}
        </ul>
        {free.length > 0 && (
          <Select
            value=""
            onValueChange={(target) =>
              onChange((d) => ({
                ...d,
                links: [...d.links, newLink(stage.key, target, nameOf(target))],
              }))
            }
          >
            <SelectTrigger
              aria-label={t('pipeline.addLink')}
              className="h-8 w-full border-dashed text-[13px]"
            >
              <Plus className="size-3.5" />
              <SelectValue placeholder={t('pipeline.addLink')} />
            </SelectTrigger>
            <SelectContent>
              {free.map((s) => (
                <SelectItem key={s.key} value={s.key}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {outs.length > 1 && (
        <label className="flex items-center gap-2 text-[13px]">
          <Switch
            checked={stage.confirmDecision}
            onCheckedChange={(v) => onChange(patchStage(stage.key, { confirmDecision: v }))}
          />
          {t('pipeline.confirmDecision')}
        </label>
      )}

      <Button
        variant="outline"
        size="sm"
        disabled={draft.stages.length === 1 || stage.activeTasks > 0}
        title={stage.activeTasks ? t('pipeline.inUse', { count: stage.activeTasks }) : undefined}
        onClick={onRemove}
      >
        <Trash2 />
        {t('pipeline.remove')}
      </Button>
    </section>
  )
}

/** One branch of a fork: its name and what makes the decider take it; none: always taken. */
export function BranchPanel({
  link,
  draft,
  onChange,
}: PanelProps & {
  link: DraftLink
}) {
  const { t } = useTranslation()
  const name = (key: string) => draft.stages.find((s) => s.key === key)?.name ?? ''
  const branches = linksFrom(draft, link.source).length
  return (
    <section
      aria-label={t('pipeline.branchPanel', { from: name(link.source), to: name(link.target) })}
      className="grid gap-3"
    >
      <p className="text-[13px]">
        {name(link.source)} → {name(link.target)}
      </p>
      {branches < 2 && (
        <p className="text-[12.5px] text-muted-foreground">{t('pipeline.notABranch')}</p>
      )}
      <Field label={t('pipeline.branchName')}>
        <Input
          value={link.name}
          maxLength={80}
          onChange={(e) => onChange(patchLink(link.key, { name: e.target.value }))}
        />
      </Field>
      <Field label={t('pipeline.condition')}>
        <Textarea
          value={link.condition}
          rows={4}
          maxLength={500}
          placeholder={t('pipeline.conditionPlaceholder')}
          onChange={(e) =>
            onChange(patchLink(link.key, { condition: e.target.value, always: false }))
          }
        />
      </Field>
      {branches > 1 && (
        <p className="text-[12.5px] text-muted-foreground">
          {link.condition.trim() && !link.always
            ? t('pipeline.conditionHelp')
            : t('pipeline.alwaysHelp')}
        </p>
      )}
      <Button
        variant="outline"
        size="sm"
        onClick={() =>
          onChange((d) => ({ ...d, links: d.links.filter((l) => l.key !== link.key) }))
        }
      >
        <Trash2 />
        {t('pipeline.removeBranch')}
      </Button>
    </section>
  )
}

/** The pipeline as a whole: rejections allowed and who decides the branches. */
export function SettingsPanel({
  draft,
  onChange,
  forks,
  direct,
  onTry,
}: PanelProps & {
  /** The stages that fork: each one’s branches can be tried. */
  forks: { key: string; name: string }[]
  direct: boolean
  onTry: (fork: string) => void
}) {
  const { t } = useTranslation()
  return (
    <section aria-label={t('pipeline.settings')} className="grid gap-3">
      <Field label={t('pipeline.maxRejections')}>
        <Input
          type="number"
          min={1}
          max={10}
          value={draft.maxRejections}
          onChange={(e) =>
            onChange((d) => ({
              ...d,
              maxRejections: Math.min(10, Math.max(1, Number(e.target.value) || 1)),
            }))
          }
          className="h-8 w-20"
        />
      </Field>
      {forks.length > 0 && (
        <>
          <h3 className="text-[13px] font-medium">{t('pipeline.decider')}</h3>
          <p className="text-[12.5px] text-muted-foreground">{t('pipeline.deciderHelp')}</p>
          <Field label={t('pipeline.deciderCli')}>
            <Select
              value={draft.deciderCli ?? NONE}
              onValueChange={(v) =>
                onChange((d) => ({
                  ...d,
                  deciderCli: v === NONE ? null : (v as DeciderCli),
                  deciderAccountId: null,
                }))
              }
            >
              <SelectTrigger className="h-9 w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{t('pipeline.deciderAuto')}</SelectItem>
                <SelectItem value="claude">{t('cli.claude')}</SelectItem>
                <SelectItem value="agy">{t('cli.agy')}</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label={t('pipeline.deciderModel')}>
            <Input
              value={draft.deciderModel}
              maxLength={80}
              placeholder={t('pipeline.deciderModelPlaceholder')}
              onChange={(e) => onChange((d) => ({ ...d, deciderModel: e.target.value }))}
            />
          </Field>
          {forks.map((fork) => (
            <Button key={fork.key} variant="outline" size="sm" onClick={() => onTry(fork.key)}>
              {forks.length > 1 ? t('pipeline.tryFork', { name: fork.name }) : t('pipeline.try')}
            </Button>
          ))}
          {direct && (
            <p role="note" className="text-[12.5px] text-muted-foreground">
              {t('pipeline.directWarning')}
            </p>
          )}
        </>
      )}
    </section>
  )
}

/** A labelled control: the label wraps it, so it names the input or the select's button. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1">
      <span className="text-[12.5px] text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}
