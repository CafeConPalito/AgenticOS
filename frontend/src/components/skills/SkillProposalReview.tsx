import { Check, X } from 'lucide-react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { KnowledgeLevel, KnowledgeScope } from '@/api/knowledge'
import {
  fetchSkillFile,
  useAcceptSkillProposal,
  useProposal,
  useRejectSkillProposal,
  useSkillDiff,
} from '@/api/skills'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'
import { relativeTime } from '@/lib/time'
import { FileOpener, LevelSelect, SkillDiffView, levelReady, pendingScripts } from './shared'

/**
 * A skill an agent proposed (CA9, CA11, CA13): its text and files, the diff against the current
 * version when it is a new one, where it came from, the level (a new skill only) and Approve /
 * Reject. «Aprobar» stays off until every executable file was opened.
 */
export function SkillProposalReview({
  versionId,
  onClose,
}: {
  versionId: string | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const proposal = useProposal(versionId)
  const data = proposal.data
  return (
    <Sheet open={versionId !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-3xl">
        <SheetHeader className="border-b">
          <SheetTitle>
            {data && !data.new_skill
              ? t('skills.proposal.titleVersion', { name: data.skill.name })
              : t('skills.proposal.title')}
          </SheetTitle>
          <SheetDescription>
            {data &&
              `${t('skills.proposal.by', { agent: data.version.author.label })}${
                data.version.author.task_title
                  ? ` ${t('skills.proposal.task', { task: data.version.author.task_title })}`
                  : ''
              } · ${relativeTime(data.version.created_at)}`}
          </SheetDescription>
        </SheetHeader>
        {!data ? (
          <Skeleton aria-busy className="m-4 h-40 rounded-lg" />
        ) : (
          <Review key={data.version.id} versionId={data.version.id} onClose={onClose} />
        )}
      </SheetContent>
    </Sheet>
  )
}

function Review({ versionId, onClose }: { versionId: string; onClose: () => void }) {
  const { t } = useTranslation()
  const data = useProposal(versionId).data!
  const accept = useAcceptSkillProposal()
  const reject = useRejectSkillProposal()
  const diff = useSkillDiff(data.new_skill ? null : data.skill.id, null, versionId)
  const [name, setName] = useState(data.skill.name)
  const [description, setDescription] = useState(String(data.header.description ?? ''))
  const [level, setLevel] = useState<KnowledgeLevel>(() => {
    const suggested = (data.suggested_scope || data.skill.scope) as KnowledgeScope
    return {
      scope: suggested,
      projectId: data.skill.project_id ?? undefined,
      agentId: data.skill.agent_id ?? data.version.author.agent_id ?? undefined,
    }
  })
  const [opened, setOpened] = useState<Set<string>>(new Set())
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const pending = pendingScripts(data.executables, opened)

  function approve() {
    accept.mutate(
      {
        versionId,
        opened_files: [...opened],
        name: name !== data.skill.name ? name : undefined,
        description: description !== data.header.description ? description : undefined,
        ...(data.new_skill
          ? {
              scope: level.scope,
              project_id: level.projectId ?? null,
              agent_id: level.agentId ?? null,
            }
          : {}),
      },
      {
        onSuccess: () => {
          toast.success(t('skills.proposal.approved'))
          onClose()
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
      {data.version.note && data.version.note !== 'Propuesta' && (
        <p className="text-[13px]">
          <span className="font-medium">{t('skills.proposal.note')}: </span>
          {data.version.note}
        </p>
      )}
      {data.new_skill && (
        <>
          <div className="grid gap-1.5">
            <Label htmlFor="proposal-name">{t('skills.editor.name')}</Label>
            <Input
              id="proposal-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="font-mono"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="proposal-description">{t('skills.editor.description')}</Label>
            <Textarea
              id="proposal-description"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            <span>{t('skills.level.label')}</span>
            <LevelSelect label={t('skills.level.label')} value={level} onChange={setLevel} />
            {data.suggested_scope && (
              <span className="text-[12px] text-muted-foreground">
                {t('skills.proposal.suggested', {
                  level: t(`skills.level.${data.suggested_scope as KnowledgeScope}`),
                })}
              </span>
            )}
          </div>
        </>
      )}
      {!data.new_skill && diff.data && (
        <section>
          <h3 className="mb-1 text-[13px] font-medium">{t('skills.proposal.diff')}</h3>
          <SkillDiffView files={diff.data.files} />
        </section>
      )}
      <section>
        <h3 className="mb-1 text-[13px] font-medium">{t('skills.sheet.body')}</h3>
        <div className="max-w-none rounded-lg border border-sep p-3 text-[13.5px] leading-relaxed [&_li]:ml-4 [&_ol]:list-decimal [&_pre]:overflow-auto [&_pre]:rounded [&_pre]:bg-muted [&_pre]:p-2 [&_ul]:list-disc">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.body}</ReactMarkdown>
        </div>
      </section>
      <section className="flex flex-col gap-2">
        <h3 className="text-[13px] font-medium">{t('skills.sheet.files')}</h3>
        {data.executables.length > 0 && (
          <p className="text-[12.5px] text-status-failed">{t('skills.proposal.scripts')}</p>
        )}
        <FileOpener
          files={data.files}
          load={(path) => fetchSkillFile(data.skill.id, path, versionId)}
          opened={opened}
          onOpened={(path) => setOpened((current) => new Set(current).add(path))}
        />
      </section>
      <div className="mt-auto flex flex-col gap-1 border-t pt-3">
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => setRejecting(true)}>
            <X />
            {t('skills.proposal.reject')}
          </Button>
          <Button
            type="button"
            disabled={
              pending.length > 0 || accept.isPending || (data.new_skill && !levelReady(level))
            }
            onClick={approve}
          >
            <Check />
            {t('skills.proposal.approve')}
          </Button>
        </div>
        {pending.length > 0 && (
          <p className="text-right text-[12px] text-status-failed">
            {t('skills.proposal.pendingScripts', { files: pending.join(', ') })}
          </p>
        )}
      </div>
      <ConfirmDialog
        open={rejecting}
        onOpenChange={setRejecting}
        destructive
        title={t('skills.proposal.rejectTitle', { name: data.skill.name })}
        description={t('skills.proposal.rejectDescription')}
        confirmLabel={t('skills.proposal.reject')}
        onConfirm={() =>
          reject.mutate(
            { versionId, reason },
            {
              onSuccess: () => {
                toast.success(t('skills.proposal.rejected'))
                onClose()
              },
              onError: (error) => toast.error(errorMessage(error)),
            },
          )
        }
      >
        <Textarea
          aria-label={t('skills.proposal.reason')}
          placeholder={t('skills.proposal.reason')}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </ConfirmDialog>
    </div>
  )
}
