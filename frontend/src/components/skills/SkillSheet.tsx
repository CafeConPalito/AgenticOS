import { Download, Pencil, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { KnowledgeLevel } from '@/api/knowledge'
import {
  type DiffFile,
  type RegistryPreview,
  exportUrl,
  fetchPreviewFile,
  fetchSkillFile,
  useApplyUpdate,
  useDeleteSkill,
  useSkill,
  useSkillOrigin,
  useUpdatePreview,
  useUpdateSkill,
} from '@/api/skills'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { errorMessage } from '@/lib/form-errors'
import { relativeTime } from '@/lib/time'
import { SkillEditor } from './SkillEditor'
import { SkillHistory } from './SkillHistory'
import { FileOpener, LevelSelect, SkillDiffView, levelReady, pendingScripts } from './shared'
import { SkillStats } from './stats/SkillStats'

/** One skill: its content, its history, its usage and, if installed from a registry, where it
 * came from and its updates. */
export function SkillSheet({ skillId, onClose }: { skillId: string | null; onClose: () => void }) {
  const { t } = useTranslation()
  const skill = useSkill(skillId)
  const data = skill.data
  return (
    <Sheet open={skillId !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-3xl">
        <SheetHeader className="border-b">
          <SheetTitle className="font-mono">{data?.name ?? '…'}</SheetTitle>
          <SheetDescription>{data?.description}</SheetDescription>
        </SheetHeader>
        {!data ? (
          <Skeleton aria-busy className="m-4 h-40 rounded-lg" />
        ) : (
          <Tabs defaultValue="content" className="min-h-0 flex-1 gap-3 overflow-auto p-4">
            <TabsList>
              <TabsTrigger value="content">{t('skills.sheet.tabs.content')}</TabsTrigger>
              <TabsTrigger value="history">{t('skills.sheet.tabs.history')}</TabsTrigger>
              <TabsTrigger value="usage">{t('skills.sheet.tabs.usage')}</TabsTrigger>
              {data.origin === 'registry' && (
                <TabsTrigger value="origin">{t('skills.sheet.tabs.origin')}</TabsTrigger>
              )}
            </TabsList>
            <TabsContent value="content">
              <Content skillId={data.id} onDeleted={onClose} />
            </TabsContent>
            <TabsContent value="history">
              <SkillHistory skillId={data.id} />
            </TabsContent>
            <TabsContent value="usage">
              <SkillStats skillId={data.id} compact />
            </TabsContent>
            {data.origin === 'registry' && (
              <TabsContent value="origin">
                <Origin skillId={data.id} />
              </TabsContent>
            )}
          </Tabs>
        )}
      </SheetContent>
    </Sheet>
  )
}

function Content({ skillId, onDeleted }: { skillId: string; onDeleted: () => void }) {
  const { t } = useTranslation()
  const skill = useSkill(skillId).data
  const update = useUpdateSkill()
  const remove = useDeleteSkill()
  const [editing, setEditing] = useState(false)
  const [confirm, setConfirm] = useState(false)
  if (!skill) return null
  const level: KnowledgeLevel = {
    scope: skill.scope,
    projectId: skill.project_id ?? undefined,
    agentId: skill.agent_id ?? undefined,
  }
  const extra = Object.entries(skill.header).filter(([k]) => k !== 'name' && k !== 'description')

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" onClick={() => setEditing(true)}>
          <Pencil />
          {t('skills.sheet.edit')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={async () => window.open(await exportUrl(skill.id), '_blank')}
        >
          <Download />
          {t('skills.actions.export')}
        </Button>
        <LevelSelect
          label={t('skills.actions.move')}
          value={level}
          onChange={(next) => {
            if (!levelReady(next)) return
            update.mutate(
              {
                id: skill.id,
                scope: next.scope,
                project_id: next.projectId ?? null,
                agent_id: next.agentId ?? null,
              },
              {
                onSuccess: () => toast.success(t('skills.sheet.moved')),
                onError: (error) => toast.error(errorMessage(error)),
              },
            )
          }}
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="ml-auto text-status-failed"
          onClick={() => setConfirm(true)}
        >
          <Trash2 />
          {t('skills.actions.delete')}
        </Button>
      </div>
      {extra.length > 0 && (
        <section>
          <h3 className="mb-1 text-[13px] font-medium">{t('skills.sheet.header')}</h3>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[12.5px]">
            {extra.map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="font-mono text-muted-foreground">{key}</dt>
                <dd className="break-all">
                  {typeof value === 'string' ? value : JSON.stringify(value)}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      <section>
        <h3 className="mb-1 text-[13px] font-medium">{t('skills.sheet.body')}</h3>
        <div className="max-w-none rounded-lg border border-sep p-3 text-[13.5px] leading-relaxed [&_h1]:text-[17px] [&_h1]:font-semibold [&_h2]:font-semibold [&_li]:ml-4 [&_ol]:list-decimal [&_pre]:overflow-auto [&_pre]:rounded [&_pre]:bg-muted [&_pre]:p-2 [&_ul]:list-disc">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{skill.body}</ReactMarkdown>
        </div>
      </section>
      <section>
        <h3 className="mb-1 text-[13px] font-medium">{t('skills.sheet.files')}</h3>
        <FileOpener files={skill.file_list} load={(path) => fetchSkillFile(skill.id, path)} />
      </section>
      {editing && (
        <SkillEditor open onClose={() => setEditing(false)} level={level} skill={skill} />
      )}
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        destructive
        title={t('skills.sheet.deleteTitle', { name: skill.name })}
        description={t('skills.sheet.deleteDescription', { count: skill.used })}
        confirmLabel={t('skills.actions.delete')}
        onConfirm={() =>
          remove.mutate(skill.id, {
            onSuccess: () => {
              toast.success(t('skills.sheet.deleted'))
              onDeleted()
            },
            onError: (error) => toast.error(errorMessage(error)),
          })
        }
      />
    </div>
  )
}

/** Where an installed skill came from, and its update with the diff first (CA17). */
function Origin({ skillId }: { skillId: string }) {
  const { t } = useTranslation()
  const origin = useSkillOrigin(skillId)
  const skill = useSkill(skillId).data
  const preview = useUpdatePreview()
  const apply = useApplyUpdate(skillId)
  const [offer, setOffer] = useState<{ preview: RegistryPreview; files: DiffFile[] } | null>(null)
  const [opened, setOpened] = useState<Set<string>>(new Set())
  const info = origin.data
  if (!info) return null
  const edited = (skill?.versions ?? 1) > 1
  const pending = offer ? pendingScripts(offer.preview.executables, opened) : []

  return (
    <div className="flex flex-col gap-3 text-[13px]">
      <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
        <dt className="text-muted-foreground">{t('skills.explore.source')}</dt>
        <dd>{info.title}</dd>
        <dt className="text-muted-foreground">{t('skills.explore.preview.repo')}</dt>
        <dd className="break-all">{info.repo_url || info.ref}</dd>
        <dt className="text-muted-foreground">{t('skills.explore.preview.revision')}</dt>
        <dd className="font-mono">{info.revision.slice(0, 12)}</dd>
        <dt className="text-muted-foreground">{t('skills.explore.preview.license')}</dt>
        <dd>{info.license || t('skills.explore.preview.noLicense')}</dd>
      </dl>
      {info.checked_at && (
        <p className="text-muted-foreground">
          {info.update_available ? t('skills.card.update') : t('skills.explore.updates.upToDate')}
          {' · '}
          {relativeTime(info.checked_at)}
        </p>
      )}
      <div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={preview.isPending}
          onClick={() =>
            preview.mutate(skillId, {
              onSuccess: (data) => {
                setOffer(data)
                setOpened(new Set())
              },
              onError: (error) => toast.error(errorMessage(error)),
            })
          }
        >
          <RefreshCw />
          {t('skills.explore.updates.see')}
        </Button>
      </div>
      {offer && (
        <section className="flex flex-col gap-3">
          <SkillDiffView files={offer.files} />
          {offer.preview.executables.length > 0 && (
            <FileOpener
              files={offer.preview.files.filter((f) => f.executable)}
              load={(path) => fetchPreviewFile(offer.preview.id, path)}
              opened={opened}
              onOpened={(path) => setOpened((s) => new Set(s).add(path))}
            />
          )}
          {edited && (
            <p className="text-[12.5px] text-status-waiting">
              {t('skills.explore.updates.editedWarning')}
            </p>
          )}
          <div>
            <Button
              type="button"
              size="sm"
              disabled={apply.isPending || pending.length > 0 || offer.files.length === 0}
              onClick={() =>
                apply.mutate(
                  { preview_id: offer.preview.id, opened_files: [...opened] },
                  {
                    onSuccess: (skill) => {
                      toast.success(t('skills.explore.updates.applied', { number: skill.version }))
                      setOffer(null)
                    },
                    onError: (error) => toast.error(errorMessage(error)),
                  },
                )
              }
            >
              {t('skills.explore.updates.apply')}
            </Button>
            {pending.length > 0 && (
              <p className="mt-1 text-[12px] text-status-failed">
                {t('skills.proposal.pendingScripts', { files: pending.join(', ') })}
              </p>
            )}
          </div>
        </section>
      )}
    </div>
  )
}
