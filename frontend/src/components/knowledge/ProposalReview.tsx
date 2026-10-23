import { Check, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useAcceptProposal,
  useDocMarkdown,
  useKnowledgeDoc,
  useRejectProposal,
  type KnowledgeDoc,
  type KnowledgeScope,
} from '@/api/knowledge'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { MarkdownEditor } from '@/components/MarkdownEditor'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'
import { relativeTime } from '@/lib/time'

const SCOPES: KnowledgeScope[] = ['general', 'project', 'agent']

/** Where the proposal will live: a level and, for a project or an agent, which one. */
function LevelPicker({
  scope,
  projectId,
  agentId,
  suggested,
  onChange,
}: {
  scope: KnowledgeScope
  projectId: string | null
  agentId: string | null
  suggested: string
  onChange: (next: {
    scope: KnowledgeScope
    projectId: string | null
    agentId: string | null
  }) => void
}) {
  const { t } = useTranslation()
  const projects = useProjects()
  const agents = useAgents()
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-[13px] font-medium">{t('knowledge.proposal.level')}</legend>
      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={scope}
          onValueChange={(value) =>
            onChange({
              scope: value as KnowledgeScope,
              projectId: value === 'project' ? projectId : null,
              agentId: value === 'agent' ? agentId : null,
            })
          }
        >
          <SelectTrigger aria-label={t('knowledge.proposal.level')} className="h-8 w-[260px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SCOPES.map((value) => (
              <SelectItem key={value} value={value}>
                {t(`knowledge.proposal.scope.${value}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {scope === 'project' && (
          <Select
            value={projectId ?? ''}
            onValueChange={(value) => onChange({ scope, projectId: value, agentId: null })}
          >
            <SelectTrigger aria-label={t('knowledge.proposal.project')} className="h-8 w-[220px]">
              <SelectValue placeholder={t('knowledge.proposal.pickProject')} />
            </SelectTrigger>
            <SelectContent>
              {(projects.data ?? []).map((project) => (
                <SelectItem key={project.id} value={project.id}>
                  {project.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {scope === 'agent' && (
          <Select
            value={agentId ?? ''}
            onValueChange={(value) => onChange({ scope, projectId: null, agentId: value })}
          >
            <SelectTrigger aria-label={t('knowledge.proposal.agent')} className="h-8 w-[220px]">
              <SelectValue placeholder={t('knowledge.proposal.pickAgent')} />
            </SelectTrigger>
            <SelectContent>
              {(agents.data ?? []).map((agent) => (
                <SelectItem key={agent.id} value={agent.id}>
                  {agent.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>
      {suggested && (
        <p className="text-[12px] text-muted-foreground">
          {t('knowledge.proposal.levelSuggested', {
            level: t(`knowledge.proposal.scope.${suggested as KnowledgeScope}`),
          })}
        </p>
      )}
    </fieldset>
  )
}

/** The documents the proposal was built on (they are never touched). */
export function SourcesList({ doc, onOpen }: { doc: KnowledgeDoc; onOpen?: (id: string) => void }) {
  const { t } = useTranslation()
  if (doc.sources.length === 0) return null
  return (
    <ul className="flex flex-col gap-1 text-[13px]">
      {doc.sources.map((source, index) => (
        <li key={source.id ?? `${source.title}-${index}`}>
          {source.id && onOpen ? (
            <button
              type="button"
              onClick={() => onOpen(source.id!)}
              className="underline-offset-2 hover:underline"
            >
              {source.title}
            </button>
          ) : (
            <span>{source.title}</span>
          )}
          {source.removed && (
            <span className="text-muted-foreground">
              {' '}
              · {t('knowledge.proposal.sourceRemoved')}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

function Form({
  doc,
  markdown,
  onDone,
  onOpenSource,
}: {
  doc: KnowledgeDoc
  markdown: string
  onDone: () => void
  onOpenSource?: (id: string) => void
}) {
  const { t } = useTranslation()
  const accept = useAcceptProposal()
  const reject = useRejectProposal()
  const replaced = useKnowledgeDoc(doc.provenance?.replaces_id ?? null)
  const [title, setTitle] = useState(doc.title)
  const [description, setDescription] = useState(doc.description)
  const [text, setText] = useState(markdown)
  const [level, setLevel] = useState({
    scope: doc.scope,
    projectId: doc.project_id,
    agentId: doc.agent_id,
  })
  const [replace, setReplace] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const provenance = doc.provenance
  const agent = provenance?.agent_name || t('knowledge.provenance.unknownAgent')
  const ownerMissing =
    (level.scope === 'project' && !level.projectId) || (level.scope === 'agent' && !level.agentId)
  const valid = title.trim() !== '' && text.trim() !== '' && !ownerMissing

  async function run(action: () => Promise<unknown>, done: string) {
    try {
      await action()
      toast.success(done)
      onDone()
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
      <section className="flex flex-col gap-1 rounded-lg border border-status-review/40 bg-subtle p-3 text-[13px]">
        <h3 className="font-medium">{t('knowledge.proposal.title')}</h3>
        <p>{t('knowledge.proposal.intro', { agent })}</p>
        {provenance && (
          <p className="text-muted-foreground">
            {[
              relativeTime(provenance.proposed_at),
              provenance.task_title
                ? t('knowledge.proposal.task', { task: provenance.task_title })
                : '',
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        )}
      </section>

      <section className="flex flex-col gap-1.5">
        <h3 className="text-[13px] font-medium">{t('knowledge.proposal.basedOn')}</h3>
        {doc.sources.length > 0 ? (
          <SourcesList doc={doc} onOpen={onOpenSource} />
        ) : (
          <p className="text-[13px] text-muted-foreground">{t('knowledge.proposal.noSources')}</p>
        )}
      </section>

      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="proposal-title">{t('knowledge.proposal.titleLabel')}</Label>
          <Input id="proposal-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="proposal-description">{t('knowledge.proposal.descriptionLabel')}</Label>
          <Textarea
            id="proposal-description"
            dictation
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t('knowledge.sheet.descriptionPlaceholder')}
            rows={2}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="proposal-text">{t('knowledge.proposal.textLabel')}</Label>
          <MarkdownEditor id="proposal-text" value={text} onChange={setText} minRows={14} />
        </div>
      </div>

      <LevelPicker
        scope={level.scope}
        projectId={level.projectId}
        agentId={level.agentId}
        suggested={provenance?.suggested_scope ?? ''}
        onChange={setLevel}
      />

      {provenance?.replaces_id && (
        <section className="flex flex-col gap-1.5 rounded-lg border p-3 text-[13px]">
          <p>
            {t('knowledge.proposal.replaces', {
              title:
                replaced.data?.title ??
                doc.sources.find((s) => s.id === provenance.replaces_id)?.title ??
                '',
            })}
          </p>
          <div className="flex items-center gap-2">
            <Switch id="proposal-replace" checked={replace} onCheckedChange={setReplace} />
            <Label htmlFor="proposal-replace">{t('knowledge.proposal.replaceOption')}</Label>
          </div>
          <p className="text-[12px] text-muted-foreground">{t('knowledge.proposal.replaceHelp')}</p>
        </section>
      )}

      {ownerMissing && (
        <p role="alert" className="text-[13px] text-status-failed">
          {t('knowledge.proposal.missingOwner')}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          disabled={!valid || accept.isPending}
          onClick={() =>
            void run(
              () =>
                accept.mutateAsync({
                  id: doc.id,
                  title: title.trim(),
                  description,
                  markdown: text,
                  scope: level.scope,
                  project_id: level.projectId,
                  agent_id: level.agentId,
                  replace,
                }),
              t('knowledge.proposal.accepted'),
            )
          }
          className="bg-primary-action text-white hover:bg-primary-action-hover"
        >
          <Check />
          {t('knowledge.proposal.accept')}
        </Button>
        <Button variant="outline" disabled={reject.isPending} onClick={() => setRejecting(true)}>
          <X />
          {t('knowledge.proposal.reject')}
        </Button>
      </div>

      <ConfirmDialog
        open={rejecting}
        onOpenChange={setRejecting}
        title={t('knowledge.proposal.rejectTitle')}
        description={t('knowledge.proposal.rejectBody')}
        confirmLabel={t('knowledge.proposal.reject')}
        destructive
        onConfirm={() =>
          void run(
            () => reject.mutateAsync({ id: doc.id, reason: reason.trim() }),
            t('knowledge.proposal.rejected'),
          )
        }
      >
        <Input
          aria-label={t('knowledge.proposal.reason')}
          placeholder={t('knowledge.proposal.reason')}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </ConfirmDialog>
    </div>
  )
}

/** The review of an agent's proposal: read it, edit it, choose its level, accept or reject. */
export function ProposalReview({
  doc,
  onDone,
  onOpenSource,
}: {
  doc: KnowledgeDoc
  onDone: () => void
  onOpenSource?: (id: string) => void
}) {
  const markdown = useDocMarkdown(doc.id, true)
  if (markdown.isPending) return <Skeleton aria-busy className="m-4 h-64" />
  return (
    <Form
      doc={doc}
      markdown={markdown.data?.markdown ?? ''}
      onDone={onDone}
      onOpenSource={onOpenSource}
    />
  )
}
