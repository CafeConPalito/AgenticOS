import { AlertTriangle, Plus, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import { useAddNote, useDeleteNote, useEditNote, useProjectMemory } from '@/api/memory'
import type { MemoryNote, Project } from '@/api/types'
import { AgentAvatar } from '@/components/agentic/primitives'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'
import { formatDateTime } from '@/lib/time'
import { NEUTRAL_COLOR } from '@/theme/palettes'

const USER_COLOR = NEUTRAL_COLOR

function NoteEditor({
  initial,
  saving,
  onSave,
  onCancel,
}: {
  initial: string
  saving: boolean
  onSave: (text: string) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const [text, setText] = useState(initial)
  return (
    <div className="flex flex-col gap-2">
      <UnsavedChangesGuard when={text !== initial} />
      <Textarea
        aria-label={t('projects.memory.noteLabel')}
        dictation
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t('projects.memory.placeholder')}
        rows={3}
        className="border-ring"
      />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={!text.trim() || text === initial || saving}
          onClick={() => onSave(text)}
          className="bg-primary-action text-white hover:bg-primary-action-hover"
        >
          {saving ? t('common.saving') : t('projects.memory.save')}
        </Button>
      </div>
    </div>
  )
}

function NoteCard({
  note,
  color,
  projectId,
}: {
  note: MemoryNote
  color: string
  projectId: string
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const edit = useEditNote(projectId)
  const remove = useDeleteNote(projectId)
  const author = note.author_kind === 'user' ? t('projects.memory.you') : note.author_name

  const save = async (text: string) => {
    try {
      await edit.mutateAsync({ id: note.id, text })
      setEditing(false)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <article
      className="rounded-xl border border-sep px-4 py-3 shadow-card bg-card-grad"
      aria-label={author}
    >
      <div className="flex items-center gap-2.5">
        <AgentAvatar name={author} color={color} size={26} />
        <span className="text-[13px] font-medium">{author}</span>
        <time dateTime={note.created_at} className="text-xs text-muted-foreground">
          {formatDateTime(note.created_at)}
        </time>
        <div className="ml-auto flex gap-1.5">
          {!editing && (
            <Button variant="outline" size="xs" onClick={() => setEditing(true)}>
              {t('projects.memory.edit')}
            </Button>
          )}
          <Button
            variant="outline"
            size="icon-xs"
            aria-label={t('projects.memory.delete')}
            onClick={() => setConfirming(true)}
          >
            <X />
          </Button>
        </div>
      </div>
      <div className="mt-2 pl-[36px]">
        {editing ? (
          <NoteEditor
            initial={note.text}
            saving={edit.isPending}
            onSave={save}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <p className="text-[13.5px] whitespace-pre-wrap">{note.text}</p>
        )}
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('projects.memory.deleteTitle')}
        description={t('projects.memory.deleteDescription')}
        confirmLabel={t('common.delete')}
        destructive
        onConfirm={() =>
          remove.mutate(note.id, { onError: (error) => toast.error(errorMessage(error)) })
        }
      />
    </article>
  )
}

export function MemoryTab({ project }: { project: Project }) {
  const { t } = useTranslation()
  const memory = useProjectMemory(project.id)
  const agents = useAgents()
  const add = useAddNote(project.id)
  const [adding, setAdding] = useState(false)

  const colors = useMemo(
    () => new Map((agents.data ?? []).map((a) => [a.id, a.color])),
    [agents.data],
  )
  // Newest first, as in the design.
  const notes = [...(memory.data?.notes ?? [])].reverse()

  const create = async (text: string) => {
    try {
      await add.mutateAsync(text)
      setAdding(false)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <div className="flex max-w-[908px] flex-col gap-3 px-6 pt-5 pb-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[15px] font-medium">{t('projects.memory.title')}</h2>
          <p className="text-xs text-muted-foreground">{t('projects.memory.help')}</p>
        </div>
        <Button variant="outline" onClick={() => setAdding(true)} disabled={adding}>
          <Plus /> {t('projects.memory.add')}
        </Button>
      </div>

      {memory.data && memory.data.size > memory.data.limit && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-lg border border-status-waiting/40 bg-status-waiting/10 px-3 py-2 text-xs"
        >
          <AlertTriangle className="size-4 text-status-waiting" />
          {t('projects.memory.tooLong', { limit: memory.data.limit.toLocaleString() })}
        </div>
      )}

      {adding && (
        <div className="rounded-xl border border-sep px-4 py-3 shadow-card bg-card-grad">
          <NoteEditor
            initial=""
            saving={add.isPending}
            onSave={create}
            onCancel={() => setAdding(false)}
          />
        </div>
      )}

      {memory.isLoading && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
      {memory.data && notes.length === 0 && !adding && (
        <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          {t('projects.memory.empty')}
        </p>
      )}
      {notes.map((note) => (
        <NoteCard
          key={note.id}
          note={note}
          projectId={project.id}
          color={
            note.author_kind === 'user'
              ? USER_COLOR
              : ((note.agent_id && colors.get(note.agent_id)) ?? USER_COLOR)
          }
        />
      ))}
    </div>
  )
}
