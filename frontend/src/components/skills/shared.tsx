import { Check, FileCode2, FileText } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAgents } from '@/api/agents'
import type { KnowledgeLevel, KnowledgeScope } from '@/api/knowledge'
import { useProjects } from '@/api/projects'
import type { DiffFile, SkillFile } from '@/api/skills'
import { LineRow, StatusLetter } from '@/components/changes/FileDiffView'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { formatBytes } from '@/lib/format'
import { cn } from '@/lib/utils'

const SCOPES: KnowledgeScope[] = ['general', 'project', 'agent']

/** A level and, for a project or an agent, which one. `label` names the whole picker. */
export function LevelSelect({
  value,
  onChange,
  label,
}: {
  value: KnowledgeLevel
  onChange: (next: KnowledgeLevel) => void
  label: string
}) {
  const { t } = useTranslation()
  const projects = useProjects().data ?? []
  const agents = useAgents().data ?? []
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-2">
      <Select
        value={value.scope}
        onValueChange={(scope) =>
          onChange({
            scope: scope as KnowledgeScope,
            projectId: scope === 'project' ? (value.projectId ?? projects[0]?.id) : undefined,
            agentId: scope === 'agent' ? (value.agentId ?? agents[0]?.id) : undefined,
          })
        }
      >
        <SelectTrigger aria-label={t('skills.level.label')} className="h-8 w-[150px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {SCOPES.map((scope) => (
            <SelectItem key={scope} value={scope}>
              {t(`skills.level.${scope}`)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {value.scope === 'project' && (
        <Select
          value={value.projectId ?? ''}
          onValueChange={(projectId) => onChange({ scope: 'project', projectId })}
        >
          <SelectTrigger aria-label={t('skills.level.project_pick')} className="h-8 w-[200px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {projects.map((project) => (
              <SelectItem key={project.id} value={project.id}>
                {project.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {value.scope === 'agent' && (
        <Select
          value={value.agentId ?? ''}
          onValueChange={(agentId) => onChange({ scope: 'agent', agentId })}
        >
          <SelectTrigger aria-label={t('skills.level.agent_pick')} className="h-8 w-[200px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {agents.map((agent) => (
              <SelectItem key={agent.id} value={agent.id}>
                {agent.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  )
}

/** A level is complete when its owner is chosen. */
export const levelReady = (level: KnowledgeLevel) =>
  level.scope === 'general' ||
  (level.scope === 'project' && !!level.projectId) ||
  (level.scope === 'agent' && !!level.agentId)

/** The diff of two versions, every file open (skills are small), in the change viewer's look. */
export function SkillDiffView({ files }: { files: DiffFile[] }) {
  const { t } = useTranslation()
  if (files.length === 0) {
    return <p className="text-[13px] text-muted-foreground">{t('skills.history.noChanges')}</p>
  }
  return (
    <div className="flex flex-col gap-3">
      {files.map(({ change, diff }) => (
        <section
          key={change.path}
          aria-label={change.path}
          className="overflow-hidden rounded-lg border border-sep bg-card"
        >
          <header className="flex items-center gap-2 border-b bg-subtle px-3 py-2 font-mono text-[12px]">
            <StatusLetter status={change.status} />
            <span className="min-w-0 flex-1 truncate">
              {change.old_path
                ? t('skills.history.renamed', { from: change.old_path, to: change.path })
                : change.path}
            </span>
            {!change.binary && (
              <span className="text-muted-foreground">
                +{change.additions} −{change.deletions}
              </span>
            )}
          </header>
          {diff.binary ? (
            <p className="px-3 py-2 text-[12.5px] text-muted-foreground">
              {t('skills.history.binary')}
            </p>
          ) : diff.too_large ? (
            <p className="px-3 py-2 text-[12.5px] text-muted-foreground">
              {t('skills.history.tooLarge')}
            </p>
          ) : (
            diff.hunks.length > 0 && (
              <table className="w-full border-collapse font-mono text-[12px] leading-5">
                <tbody>
                  {diff.hunks.flatMap((hunk, h) =>
                    hunk.lines.map((line, i) => <LineRow key={`${h}-${i}`} line={line} />),
                  )}
                </tbody>
              </table>
            )
          )}
        </section>
      ))}
    </div>
  )
}

/**
 * The files of a skill, each one opened on demand. With `opened` and `onOpened`, the executable
 * ones must be opened before approving or installing (CA13, CA18): the opened ones are marked.
 */
export function FileOpener({
  files,
  load,
  opened,
  onOpened,
}: {
  files: SkillFile[]
  load: (path: string) => Promise<string>
  opened?: Set<string>
  onOpened?: (path: string) => void
}) {
  const { t } = useTranslation()
  const [shown, setShown] = useState<{ path: string; text: string } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  async function open(path: string) {
    if (shown?.path === path) {
      setShown(null)
      return
    }
    setBusy(path)
    try {
      setShown({ path, text: await load(path) })
      onOpened?.(path)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <ul className="overflow-hidden rounded-lg border border-sep">
        {files.map((file) => {
          const Icon = file.executable ? FileCode2 : FileText
          const seen = opened?.has(file.path)
          return (
            <li key={file.path} className="border-b border-sep last:border-b-0">
              <button
                type="button"
                onClick={() => void open(file.path)}
                aria-label={t('skills.proposal.openFile', { path: file.path })}
                aria-expanded={shown?.path === file.path}
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-2 text-left text-[12.5px] hover:bg-accent',
                  file.executable && !seen && 'bg-[var(--diff-del-bg)]',
                )}
              >
                <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1 truncate font-mono">{file.path}</span>
                {file.executable && (
                  <span className="rounded bg-status-failed/15 px-1.5 text-[11px] text-status-failed">
                    {t('skills.editor.executable')}
                  </span>
                )}
                {seen && (
                  <span className="flex items-center gap-1 text-[11px] text-status-done">
                    <Check className="size-3" aria-hidden />
                    {t('skills.proposal.opened')}
                  </span>
                )}
                <span className="text-[11px] text-muted-foreground">{formatBytes(file.size)}</span>
                {busy === file.path && <span aria-busy className="size-3 animate-pulse" />}
              </button>
            </li>
          )
        })}
      </ul>
      {shown && (
        <pre
          aria-label={shown.path}
          className="max-h-[360px] overflow-auto rounded-lg border border-sep bg-subtle p-3 font-mono text-[12px] whitespace-pre-wrap"
        >
          {shown.text}
        </pre>
      )}
    </div>
  )
}

/** Executables not opened yet: what blocks approving or installing. */
export const pendingScripts = (executables: string[], opened: Set<string>) =>
  executables.filter((path) => !opened.has(path))

export function CloseButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation()
  return (
    <Button type="button" variant="outline" size="sm" onClick={onClick}>
      {t('skills.actions.close')}
    </Button>
  )
}
