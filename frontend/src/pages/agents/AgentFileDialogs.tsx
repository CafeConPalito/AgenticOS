import { Copy, FileUp, Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import {
  type ImportPreview,
  useAgentTemplates,
  useDeleteTemplate,
  useDuplicateTemplate,
  useImportAgent,
  usePreviewImport,
  useUpdateTemplate,
} from '@/api/agents'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { errorMessage } from '@/lib/form-errors'

/** «Importar agente» (phase 19): a file exported from Agentic OS, previewed before it becomes a
 * draft; what this installation does not have is listed and left out. */
export function ImportAgentDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const previewer = usePreviewImport()
  const importer = useImportAgent()
  const [payload, setPayload] = useState<unknown>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [name, setName] = useState('')

  function reset(next: boolean) {
    if (!next) {
      setPayload(null)
      setPreview(null)
      setName('')
    }
    onOpenChange(next)
  }

  async function read(file: File) {
    try {
      const parsed: unknown = JSON.parse(await file.text())
      const result = await previewer.mutateAsync(parsed)
      setPayload(parsed)
      setPreview(result)
      setName(String(result.agent.name ?? ''))
    } catch (error) {
      toast.error(
        error instanceof SyntaxError ? t('agentTemplates.import.notJson') : errorMessage(error),
      )
    }
  }

  async function run() {
    try {
      const result = await importer.mutateAsync({ payload, name: name.trim() || undefined })
      toast.success(t('agentTemplates.import.done', { name: result.agent.name }))
      for (const note of result.notes) toast.warning(note)
      reset(false)
      navigate(`/agentes/${result.agent.id}/resumen`)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const missing = preview
    ? [
        ...preview.missing_skills.map((x) => t('agentTemplates.import.missingSkill', { name: x })),
        ...preview.missing_connections.map((x) =>
          t('agentTemplates.import.missingConnection', { name: x }),
        ),
        ...preview.missing_knowledge.map((x) =>
          t('agentTemplates.import.missingDocument', { name: x }),
        ),
      ]
    : []

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t('agentTemplates.import.title')}</DialogTitle>
          <DialogDescription>{t('agentTemplates.import.description')}</DialogDescription>
        </DialogHeader>
        {!preview ? (
          <Label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed border-input p-6 text-center font-normal hover:border-ring">
            <FileUp className="size-5 text-muted-foreground" aria-hidden />
            {t('agentTemplates.import.pick')}
            <input
              type="file"
              accept=".json,application/json"
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void read(file)
              }}
            />
          </Label>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="import-name">{t('agents.fields.name')}</Label>
              <Input id="import-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <p className="text-[12.5px] text-muted-foreground">
              {preview.agent.role} · {preview.agent.cli && t(`cli.${preview.agent.cli}`)}
              {preview.own_skills.length > 0 &&
                ` · ${t('agentTemplates.import.ownSkills', { count: preview.own_skills.length })}`}
            </p>
            {!preview.cli_installed && (
              <p className="text-[12.5px] text-status-waiting">
                {t('agentTemplates.import.cliMissing')}
              </p>
            )}
            {missing.length > 0 && (
              <div>
                <p className="text-[12.5px] font-medium">{t('agentTemplates.import.leftOut')}</p>
                <ul className="mt-1 list-disc pl-5 text-[12.5px] text-muted-foreground">
                  {missing.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-[12px] text-muted-foreground">
              {t('agentTemplates.import.asDraft')}
            </p>
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => reset(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            disabled={!preview || importer.isPending}
            onClick={() => void run()}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('agentTemplates.import.run')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** «Mis plantillas» (phase 19): the person's templates, renamed, duplicated or deleted here. */
export function TemplatesDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const own = (useAgentTemplates().data ?? []).filter((x) => x.own)
  const update = useUpdateTemplate()
  const duplicate = useDuplicateTemplate()
  const remove = useDeleteTemplate()
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null)
  const onError = (error: unknown) => toast.error(errorMessage(error))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{t('agentTemplates.title')}</DialogTitle>
          <DialogDescription>{t('agentTemplates.description')}</DialogDescription>
        </DialogHeader>
        {own.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">{t('agentTemplates.empty')}</p>
        ) : (
          <ul className="flex flex-col divide-y divide-sep rounded-lg border border-sep">
            {own.map((template) => (
              <li key={template.id} className="flex items-center gap-2 px-3 py-2">
                {editing?.id === template.id ? (
                  <form
                    className="flex flex-1 gap-2"
                    onSubmit={(event) => {
                      event.preventDefault()
                      update.mutate(
                        { id: template.id, name: editing.name },
                        { onSuccess: () => setEditing(null), onError },
                      )
                    }}
                  >
                    <Input
                      aria-label={t('agentTemplates.name')}
                      value={editing.name}
                      onChange={(e) => setEditing({ id: template.id, name: e.target.value })}
                    />
                    <Button type="submit" size="sm">
                      {t('common.save')}
                    </Button>
                  </form>
                ) : (
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{template.name}</span>
                    <span className="text-[12px] text-muted-foreground">{template.role}</span>
                  </span>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('agentTemplates.rename', { name: template.name })}
                  onClick={() => setEditing({ id: template.id, name: template.name })}
                >
                  <Pencil />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('agentTemplates.duplicate', { name: template.name })}
                  onClick={() => duplicate.mutate(template.id, { onError })}
                >
                  <Copy />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('agentTemplates.delete', { name: template.name })}
                  onClick={() => remove.mutate(template.id, { onError })}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  )
}
