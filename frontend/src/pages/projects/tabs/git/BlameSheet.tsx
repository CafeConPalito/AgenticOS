import { useTranslation } from 'react-i18next'
import { useBlame } from '@/api/git'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { relativeTime } from '@/lib/time'

/** Who last changed each line of a file, in groups of lines that come from the same commit. */
export function BlameSheet({
  repoId,
  path,
  onClose,
}: {
  repoId: string
  path: string | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const blame = useBlame(repoId, path)
  return (
    <Sheet open={path !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-4xl">
        <SheetHeader className="border-b">
          <SheetTitle>{t('git.blame.title', { path: path ?? '' })}</SheetTitle>
          <SheetDescription>{t('git.blame.description')}</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {blame.isPending ? (
            <Skeleton aria-busy className="h-40 rounded-lg" />
          ) : blame.isError ? (
            <p role="alert" className="text-[13px] text-status-failed">
              {t('git.blame.error')}
            </p>
          ) : (
            <div className="overflow-hidden rounded-lg border border-sep bg-card font-mono text-[12px]">
              {blame.data.map((group) => (
                <section
                  key={`${group.start}-${group.sha}`}
                  aria-label={`${group.short} ${group.start}`}
                  className="grid grid-cols-[210px_1fr] border-b border-sep last:border-b-0"
                >
                  <div className="flex flex-col gap-0.5 border-r border-sep bg-subtle px-3 py-1.5 font-sans text-xs">
                    <span className="flex items-center gap-2">
                      <span className="font-mono">{group.short}</span>
                      {group.agent_name && <Badge variant="outline">{group.agent_name}</Badge>}
                    </span>
                    <span className="truncate" title={group.summary}>
                      {group.summary}
                    </span>
                    <span className="text-muted-foreground">
                      {group.author} · {relativeTime(group.date)}
                    </span>
                  </div>
                  <table className="w-full border-collapse leading-5">
                    <tbody>
                      {group.text.map((line, offset) => (
                        <tr key={offset}>
                          <td className="w-10 px-2 text-right text-muted-foreground/70 select-none">
                            {group.start + offset}
                          </td>
                          <td className="pr-3 break-all whitespace-pre-wrap">{line}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              ))}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
