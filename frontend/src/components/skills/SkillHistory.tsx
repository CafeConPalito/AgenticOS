import type { TFunction } from 'i18next'
import { RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { type SkillVersion, useRestoreVersion, useSkillDiff, useSkillVersions } from '@/api/skills'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/form-errors'
import { relativeTime } from '@/lib/time'
import { cn } from '@/lib/utils'
import { SkillDiffView } from './shared'

function authorText(version: SkillVersion, t: TFunction): string {
  return t(`skills.history.by.${version.author.kind}`, { label: version.author.label })
}

/** Every version of a skill, the diff between any two and «Restaurar» (CA12). */
export function SkillHistory({ skillId }: { skillId: string }) {
  const { t } = useTranslation()
  const versions = useSkillVersions(skillId)
  const restore = useRestoreVersion(skillId)
  const [from, setFrom] = useState<string | null>(null)
  const [to, setTo] = useState<string | null>(null)
  const diff = useSkillDiff(skillId, from, to)

  if (versions.isPending) return <Skeleton aria-busy className="h-32 rounded-lg" />
  const list = versions.data ?? []
  const accepted = list.filter((v) => v.status === 'accepted')

  return (
    <div className="flex flex-col gap-4">
      <ol aria-label={t('skills.history.title')} className="flex flex-col gap-1.5">
        {list.map((version) => (
          <li
            key={version.id}
            className={cn(
              'flex items-start gap-3 rounded-lg border border-sep px-3 py-2',
              version.status !== 'accepted' && 'opacity-70',
            )}
          >
            <span className="font-mono text-[12.5px] font-medium">
              {t('skills.card.version', { number: version.number })}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[12.5px]">
                {authorText(version, t)}
                <span className="text-muted-foreground"> · {relativeTime(version.created_at)}</span>
                {version.current && (
                  <span className="ml-2 rounded bg-accent px-1.5 text-[11px]">
                    {t('skills.history.current')}
                  </span>
                )}
                {version.status !== 'accepted' && (
                  <span className="ml-2 rounded bg-subtle px-1.5 text-[11px]">
                    {t(`skills.history.status.${version.status}`)}
                  </span>
                )}
              </p>
              {version.note && (
                <p className="truncate text-[12px] text-muted-foreground">{version.note}</p>
              )}
            </div>
            {!version.current && version.status === 'accepted' && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={restore.isPending}
                aria-label={t('skills.history.restoreVersion', { number: version.number })}
                onClick={() =>
                  restore.mutate(version.id, {
                    onSuccess: (skill) =>
                      toast.success(t('skills.history.restored', { number: skill.version })),
                    onError: (error) => toast.error(errorMessage(error)),
                  })
                }
              >
                <RotateCcw />
                {t('skills.actions.restore')}
              </Button>
            )}
          </li>
        ))}
      </ol>
      {accepted.length > 1 && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
            <span>{t('skills.actions.compare')}</span>
            <VersionSelect
              label={t('skills.history.from')}
              versions={list}
              value={from}
              onChange={setFrom}
            />
            <VersionSelect
              label={t('skills.history.to')}
              versions={list}
              value={to}
              onChange={setTo}
            />
          </div>
          {diff.data && (
            <>
              <p className="text-[12px] text-muted-foreground">
                {t('skills.history.range', {
                  from: diff.data.from_version ?? 0,
                  to: diff.data.to_version,
                })}
              </p>
              <SkillDiffView files={diff.data.files} />
            </>
          )}
        </section>
      )}
    </div>
  )
}

const AUTO = 'auto'

function VersionSelect({
  label,
  versions,
  value,
  onChange,
}: {
  label: string
  versions: SkillVersion[]
  value: string | null
  onChange: (id: string | null) => void
}) {
  const { t } = useTranslation()
  return (
    <Select value={value ?? AUTO} onValueChange={(v) => onChange(v === AUTO ? null : v)}>
      <SelectTrigger aria-label={label} className="h-8 w-[140px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={AUTO}>{label}</SelectItem>
        {versions
          .filter((v) => v.files > 0)
          .map((v) => (
            <SelectItem key={v.id} value={v.id}>
              {t('skills.card.version', { number: v.number })}
            </SelectItem>
          ))}
      </SelectContent>
    </Select>
  )
}
