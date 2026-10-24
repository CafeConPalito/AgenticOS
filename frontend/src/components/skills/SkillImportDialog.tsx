import { isTauri } from '@tauri-apps/api/core'
import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { KnowledgeLevel } from '@/api/knowledge'
import {
  type CliSkill,
  type ImportResult,
  levelBody,
  useCliSkills,
  useImportCliSkills,
  useImportSkill,
} from '@/api/skills'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { errorMessage } from '@/lib/form-errors'
import { pickFiles } from '@/lib/native-files'
import { LevelSelect, levelReady } from './shared'

function report(results: ImportResult[], t: TFunction) {
  const done = results.filter((r) => r.skill)
  if (done.length) toast.success(t('skills.import.done', { count: done.length }))
  for (const result of results) {
    if (result.renamed_to && result.skill) {
      toast.info(
        t('skills.import.renamed', {
          from: result.path.split(/[\\/]/).pop(),
          to: result.renamed_to,
        }),
      )
    }
    if (!result.skill) {
      toast.error(result.path, {
        description: t(`skills.errors.${result.error_code ?? 'unknown'}`, {
          defaultValue: result.message ?? '',
        }),
      })
    }
  }
}

/** Importing skills (CA2): a folder, a .zip or a SKILL.md on this computer, or the skills the
 * person already has in their CLIs, each one to the level they choose. Originals are only read. */
export function SkillImportDialog({
  open,
  onClose,
  level,
}: {
  open: boolean
  onClose: () => void
  level: KnowledgeLevel
}) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('skills.import.title')}</DialogTitle>
          <DialogDescription>{t('skills.import.pathHint')}</DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="path" className="gap-3">
          <TabsList>
            <TabsTrigger value="path">{t('skills.import.fromPath')}</TabsTrigger>
            <TabsTrigger value="clis">{t('skills.import.fromClis')}</TabsTrigger>
          </TabsList>
          <TabsContent value="path">
            <FromPath level={level} onDone={onClose} />
          </TabsContent>
          <TabsContent value="clis">
            <FromClis level={level} onDone={onClose} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

function FromPath({ level, onDone }: { level: KnowledgeLevel; onDone: () => void }) {
  const { t } = useTranslation()
  const [path, setPath] = useState('')
  const [target, setTarget] = useState<KnowledgeLevel>(level)
  const run = useImportSkill(target)
  const desktop = isTauri()

  async function browse(folder: boolean) {
    if (folder) {
      const { open } = await import('@tauri-apps/plugin-dialog')
      const picked = await open({
        directory: true,
        multiple: false,
        title: t('skills.import.title'),
      })
      if (typeof picked === 'string') setPath(picked)
      return
    }
    const [picked] = await pickFiles(t('skills.import.title'), false)
    if (picked) setPath(picked)
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      report([await run.mutateAsync(path.trim())], t)
      onDone()
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <div className="grid gap-1.5">
        <Label htmlFor="skill-import-path">{t('skills.import.fromPath')}</Label>
        <div className="flex gap-2">
          <Input
            id="skill-import-path"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className="font-mono"
          />
          {desktop && (
            <>
              <Button type="button" variant="outline" onClick={() => void browse(true)}>
                {t('skills.import.browseFolder')}
              </Button>
              <Button type="button" variant="outline" onClick={() => void browse(false)}>
                {t('skills.import.browse')}
              </Button>
            </>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 text-[13px]">
        <span>{t('skills.import.importTo')}</span>
        <LevelSelect label={t('skills.import.importTo')} value={target} onChange={setTarget} />
      </div>
      <div className="flex justify-end">
        <Button type="submit" disabled={!path.trim() || !levelReady(target) || run.isPending}>
          {t('skills.import.doImport')}
        </Button>
      </div>
    </form>
  )
}

function sourceLabel(item: CliSkill, t: TFunction) {
  return t(`skills.import.source.${item.source}`, { project: item.project_name })
}

/** The CLIs' skills, with a box and a level per row (decision 1 of the spec). */
export function FromClis({
  level,
  onDone,
  only,
}: {
  level: KnowledgeLevel
  onDone?: () => void
  /** Only these sources (a project shows its repository's). */
  only?: (item: CliSkill) => boolean
}) {
  const { t } = useTranslation()
  const scan = useCliSkills(true)
  const run = useImportCliSkills()
  const [picked, setPicked] = useState<Record<string, KnowledgeLevel>>({})
  if (scan.isPending) return <Skeleton aria-busy className="h-24 rounded-lg" />
  const items = (scan.data ?? []).filter((item) => !only || only(item))
  if (items.length === 0) {
    return <p className="text-[13px] text-muted-foreground">{t('skills.import.noneFound')}</p>
  }
  const chosen = Object.entries(picked)

  async function submit() {
    try {
      report(
        await run.mutateAsync(chosen.map(([path, target]) => ({ path, ...levelBody(target) }))),
        t,
      )
      setPicked({})
      onDone?.()
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[12.5px] text-muted-foreground">{t('skills.import.clisHint')}</p>
      <ul className="flex max-h-[360px] flex-col gap-1.5 overflow-auto">
        {items.map((item) => {
          const target = picked[item.path]
          return (
            <li key={item.path} className="rounded-lg border border-sep px-3 py-2">
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  aria-label={t('skills.import.pick', { name: item.name })}
                  disabled={!!item.error}
                  checked={!!target}
                  onChange={(e) =>
                    setPicked((current) => {
                      const next = { ...current }
                      if (e.target.checked) next[item.path] = level
                      else delete next[item.path]
                      return next
                    })
                  }
                />
                <div className="min-w-0 flex-1">
                  <p className="text-[13px]">
                    <span className="font-mono font-medium">{item.name}</span>
                    <span className="text-muted-foreground"> · {sourceLabel(item, t)}</span>
                    {item.imported && (
                      <span className="ml-2 rounded bg-subtle px-1.5 text-[11px]">
                        {t('skills.import.already')}
                      </span>
                    )}
                  </p>
                  <p className="line-clamp-2 text-[12px] text-muted-foreground">
                    {item.error || item.description}
                  </p>
                </div>
              </div>
              {target && (
                <div className="mt-2 pl-6">
                  <LevelSelect
                    label={t('skills.import.levelFor', { name: item.name })}
                    value={target}
                    onChange={(next) => setPicked((c) => ({ ...c, [item.path]: next }))}
                  />
                </div>
              )}
            </li>
          )
        })}
      </ul>
      <div className="flex justify-end">
        <Button
          type="button"
          disabled={chosen.length === 0 || chosen.some(([, l]) => !levelReady(l)) || run.isPending}
          onClick={() => void submit()}
        >
          {t('skills.import.importSelected', { count: chosen.length })}
        </Button>
      </div>
    </div>
  )
}
