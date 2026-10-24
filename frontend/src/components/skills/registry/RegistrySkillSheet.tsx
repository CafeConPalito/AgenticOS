import { ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { KnowledgeLevel } from '@/api/knowledge'
import { type RegistryPreview, fetchPreviewFile, levelBody, useInstallSkill } from '@/api/skills'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { errorMessage } from '@/lib/form-errors'
import { FileOpener, LevelSelect, levelReady, pendingScripts } from '../shared'

/** What the source says about the skill's safety (skills.sh's three tools, ClawHub's flag). */
function Security({ security }: { security: Record<string, unknown> }) {
  const { t } = useTranslation()
  const lines: string[] = []
  const skillsSh = security.skills_sh as Record<string, { risk?: string }> | undefined
  if (skillsSh) {
    for (const [tool, value] of Object.entries(skillsSh)) {
      if (value?.risk) lines.push(t('skills.explore.preview.risk', { tool, risk: value.risk }))
    }
  }
  const clawhub = security.clawhub as { suspicious?: boolean } | undefined
  if (clawhub?.suspicious) lines.push(t('skills.explore.preview.suspicious'))
  if (lines.length === 0) return null
  return (
    <section className="flex flex-col gap-1">
      <h3 className="flex items-center gap-1.5 text-[13px] font-medium">
        <ShieldAlert className="size-4" aria-hidden />
        {t('skills.explore.preview.security')}
      </h3>
      <ul className="ml-5 list-disc text-[12.5px]">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  )
}

/**
 * A registry skill before installing it (CA16): its SKILL.md, its files with the executables
 * marked, license, revision and the source's security analysis; «Instalar en…» a level. The
 * install is exactly this download, and needs every executable opened first (CA18).
 */
export function RegistrySkillSheet({
  preview,
  onClose,
}: {
  preview: RegistryPreview | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  return (
    <Sheet open={preview !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-3xl">
        {preview && <Content key={preview.id} preview={preview} onClose={onClose} />}
        {!preview && (
          <SheetHeader>
            <SheetTitle>{t('skills.explore.preview.loading')}</SheetTitle>
          </SheetHeader>
        )}
      </SheetContent>
    </Sheet>
  )
}

function Content({ preview, onClose }: { preview: RegistryPreview; onClose: () => void }) {
  const { t } = useTranslation()
  const install = useInstallSkill()
  const [level, setLevel] = useState<KnowledgeLevel>({ scope: 'general' })
  const [opened, setOpened] = useState<Set<string>>(new Set())
  const pending = pendingScripts(preview.executables, opened)

  function submit() {
    install.mutate(
      { preview_id: preview.id, opened_files: [...opened], ...levelBody(level) },
      {
        onSuccess: ({ renamed_to }) => {
          toast.success(
            renamed_to
              ? t('skills.explore.preview.renamed', { name: renamed_to })
              : t('skills.explore.preview.installed'),
          )
          onClose()
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  return (
    <>
      <SheetHeader className="border-b">
        <SheetTitle className="font-mono">{preview.name}</SheetTitle>
        <SheetDescription>{String(preview.header.description ?? '')}</SheetDescription>
      </SheetHeader>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[12.5px]">
          <dt className="text-muted-foreground">{t('skills.explore.source')}</dt>
          <dd>
            {t(`skills.explore.sources.${preview.card.source}`, {
              defaultValue: preview.card.source,
            })}
          </dd>
          <dt className="text-muted-foreground">{t('skills.explore.preview.repo')}</dt>
          <dd className="break-all">
            {preview.repo_url ? (
              <a href={preview.repo_url} target="_blank" rel="noreferrer" className="underline">
                {preview.repo_url}
              </a>
            ) : (
              preview.card.ref
            )}
          </dd>
          <dt className="text-muted-foreground">{t('skills.explore.preview.revision')}</dt>
          <dd className="font-mono">{preview.revision.slice(0, 12)}</dd>
          <dt className="text-muted-foreground">{t('skills.explore.preview.license')}</dt>
          <dd>{preview.license || t('skills.explore.preview.noLicense')}</dd>
        </dl>
        <Security security={preview.security} />
        <p role="note" className="text-[12.5px] text-status-waiting">
          {t('skills.explore.warning')}
        </p>
        <section>
          <h3 className="mb-1 text-[13px] font-medium">{t('skills.sheet.body')}</h3>
          <div className="max-w-none rounded-lg border border-sep p-3 text-[13.5px] leading-relaxed [&_li]:ml-4 [&_ol]:list-decimal [&_pre]:overflow-auto [&_pre]:rounded [&_pre]:bg-muted [&_pre]:p-2 [&_ul]:list-disc">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{preview.body}</ReactMarkdown>
          </div>
        </section>
        <section className="flex flex-col gap-2">
          <h3 className="text-[13px] font-medium">{t('skills.sheet.files')}</h3>
          {preview.executables.length > 0 && (
            <p className="text-[12.5px] text-status-failed">{t('skills.proposal.scripts')}</p>
          )}
          <FileOpener
            files={preview.files}
            load={(path) => fetchPreviewFile(preview.id, path)}
            opened={opened}
            onOpened={(path) => setOpened((current) => new Set(current).add(path))}
          />
        </section>
        <div className="mt-auto flex flex-col gap-1 border-t pt-3">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="text-[13px]">{t('skills.explore.preview.installTo')}</span>
            <LevelSelect
              label={t('skills.explore.preview.installTo')}
              value={level}
              onChange={setLevel}
            />
            <Button
              type="button"
              disabled={pending.length > 0 || !levelReady(level) || install.isPending}
              onClick={submit}
            >
              {t('skills.explore.preview.install')}
            </Button>
          </div>
          {pending.length > 0 && (
            <p className="text-right text-[12px] text-status-failed">
              {t('skills.proposal.pendingScripts', { files: pending.join(', ') })}
            </p>
          )}
        </div>
      </div>
    </>
  )
}
