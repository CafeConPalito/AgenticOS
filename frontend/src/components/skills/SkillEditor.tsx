import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { KnowledgeLevel } from '@/api/knowledge'
import {
  type FileInput,
  type SkillDetail,
  fetchSkillFile,
  useCreateSkill,
  useSaveSkill,
} from '@/api/skills'
import { MarkdownEditor } from '@/components/MarkdownEditor'
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
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'

interface Draft {
  name: string
  description: string
  body: string
  /** Support files the person touched: new text, or null to remove. */
  files: Record<string, string | null>
  note: string
}

const EXECUTABLE = /\.(py|sh|bash|ps1|bat|cmd|js|mjs|cjs|ts|rb|pl|php)$/i

/**
 * Creates a skill (at `level`) or saves a new version of `skill`: name, description, body and
 * the support files. Every save is a new version, with an optional note (CA12).
 */
export function SkillEditor({
  open,
  onClose,
  level,
  skill,
}: {
  open: boolean
  onClose: () => void
  level: KnowledgeLevel
  skill?: SkillDetail
}) {
  const { t } = useTranslation()
  const create = useCreateSkill(level)
  const save = useSaveSkill(skill?.id ?? '')
  const [draft, setDraft] = useState<Draft>(() => ({
    name: skill?.name ?? '',
    description: skill?.description ?? '',
    body: skill?.body ?? '',
    files: {},
    note: '',
  }))
  const [newPath, setNewPath] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const existing = (skill?.file_list ?? []).filter((f) => f.path !== 'SKILL.md')
  const paths = [
    ...existing.map((f) => f.path).filter((p) => draft.files[p] !== null),
    ...Object.keys(draft.files).filter(
      (p) => draft.files[p] !== null && !existing.some((f) => f.path === p),
    ),
  ]
  const busy = create.isPending || save.isPending

  async function edit(path: string) {
    if (editing === path) return setEditing(null)
    if (draft.files[path] === undefined && skill) {
      const text = await fetchSkillFile(skill.id, path)
      setDraft((d) => ({ ...d, files: { ...d.files, [path]: text } }))
    }
    setEditing(path)
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const files: Record<string, FileInput | null> = {}
    for (const [path, text] of Object.entries(draft.files)) {
      files[path] = text === null ? null : { text }
    }
    try {
      if (skill) {
        const saved = await save.mutateAsync({
          name: draft.name !== skill.name ? draft.name : undefined,
          description: draft.description !== skill.description ? draft.description : undefined,
          body: draft.body !== skill.body ? draft.body : undefined,
          files,
          note: draft.note || undefined,
        })
        toast.success(t('skills.editor.saved', { number: saved.version }))
      } else {
        const created = await create.mutateAsync({
          name: draft.name.trim(),
          description: draft.description,
          body: draft.body,
          files: files as Record<string, FileInput>,
          note: draft.note || undefined,
        })
        toast.success(t('skills.editor.created', { name: created.name }))
      }
      onClose()
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-3xl">
        <SheetHeader className="border-b">
          <SheetTitle>
            {skill
              ? t('skills.editor.titleEdit', { name: skill.name })
              : t('skills.editor.titleNew')}
          </SheetTitle>
          <SheetDescription>{t('skills.editor.nameHint')}</SheetDescription>
        </SheetHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
          <div className="grid gap-1.5">
            <Label htmlFor="skill-name">{t('skills.editor.name')}</Label>
            <Input
              id="skill-name"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              className="font-mono"
              required
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="skill-description">{t('skills.editor.description')}</Label>
            <Textarea
              id="skill-description"
              value={draft.description}
              maxLength={1024}
              rows={3}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              required
            />
            <p className="text-[12px] text-muted-foreground">
              {t('skills.editor.descriptionHint', { count: draft.description.length })}
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="skill-body">{t('skills.editor.body')}</Label>
            <MarkdownEditor
              id="skill-body"
              value={draft.body}
              onChange={(body) => setDraft({ ...draft, body })}
              minRows={12}
            />
          </div>
          <fieldset className="grid gap-2">
            <legend className="mb-1 text-[13px] font-medium">{t('skills.editor.files')}</legend>
            <ul className="flex flex-col gap-1.5">
              {paths.map((path) => (
                <li key={path} className="rounded-lg border border-sep">
                  <div className="flex items-center gap-2 px-2.5 py-1.5">
                    <button
                      type="button"
                      onClick={() => void edit(path)}
                      className="min-w-0 flex-1 truncate text-left font-mono text-[12.5px]"
                    >
                      {path}
                    </button>
                    {EXECUTABLE.test(path) && (
                      <span className="text-[11px] text-status-failed">
                        {t('skills.editor.executable')}
                      </span>
                    )}
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      aria-label={t('skills.editor.removeFile', { path })}
                      onClick={() =>
                        setDraft({ ...draft, files: { ...draft.files, [path]: null } })
                      }
                    >
                      <Trash2 />
                    </Button>
                  </div>
                  {editing === path && (
                    <Textarea
                      aria-label={t('skills.editor.fileContent', { path })}
                      value={draft.files[path] ?? ''}
                      rows={8}
                      className="rounded-none border-0 border-t font-mono text-[12px]"
                      onChange={(e) =>
                        setDraft({ ...draft, files: { ...draft.files, [path]: e.target.value } })
                      }
                    />
                  )}
                </li>
              ))}
            </ul>
            <div className="flex gap-2">
              <Input
                aria-label={t('skills.editor.newPath')}
                placeholder={t('skills.editor.newPath')}
                value={newPath}
                onChange={(e) => setNewPath(e.target.value)}
                className="font-mono"
              />
              <Button
                type="button"
                variant="outline"
                disabled={!newPath.trim()}
                onClick={() => {
                  const path = newPath.trim()
                  setDraft({ ...draft, files: { ...draft.files, [path]: '' } })
                  setEditing(path)
                  setNewPath('')
                }}
              >
                <Plus />
                {t('skills.editor.addFile')}
              </Button>
            </div>
          </fieldset>
          {skill && (
            <div className="grid gap-1.5">
              <Label htmlFor="skill-note">{t('skills.editor.note')}</Label>
              <Input
                id="skill-note"
                value={draft.note}
                maxLength={500}
                onChange={(e) => setDraft({ ...draft, note: e.target.value })}
              />
            </div>
          )}
          <div className="mt-auto flex justify-end gap-2 border-t pt-3">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('skills.actions.cancel')}
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? t('skills.actions.saving') : t('skills.actions.save')}
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  )
}
