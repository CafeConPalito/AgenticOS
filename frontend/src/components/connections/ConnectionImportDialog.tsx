import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { KnowledgeLevel } from '@/api/knowledge'
import { useImportConnections, useScanConnections } from '@/api/connections'
import { LevelSelect } from '@/components/skills/shared'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { connectionError } from './shared'

/** The MCP servers the person already has in Claude Code and agy: pick which to bring, and
 * where to give each one. The originals are read, never changed (CA9). */
export function ConnectionImportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const found = useScanConnections(open)
  const run = useImportConnections()
  const [chosen, setChosen] = useState<Record<string, KnowledgeLevel>>({})
  const [error, setError] = useState<string | null>(null)
  const ids = Object.keys(chosen)

  async function submit() {
    setError(null)
    try {
      const result = await run.mutateAsync(ids.map((id) => ({ id, level: chosen[id] })))
      if (result.created.length > 0) {
        toast.success(t('connections.import.done', { count: result.created.length }))
      }
      if (result.problems.length > 0) {
        setError(result.problems.map((p) => `${p.name || p.id}: ${p.reason}`).join(' · '))
      } else {
        setChosen({})
        onClose()
      }
    } catch (failed) {
      setError(connectionError(failed))
    }
  }

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-3xl">
        <SheetHeader className="border-b">
          <SheetTitle>{t('connections.import.title')}</SheetTitle>
          <SheetDescription>{t('connections.import.description')}</SheetDescription>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4">
          {found.isPending ? (
            <Skeleton aria-busy className="h-20 rounded-lg" />
          ) : (found.data ?? []).length === 0 ? (
            <p className="text-[13px] text-muted-foreground">{t('connections.import.empty')}</p>
          ) : (
            <ul className="grid gap-2">
              {(found.data ?? []).map((item) => {
                const level = chosen[item.id]
                return (
                  <li key={item.id} className="grid gap-2 rounded-lg border p-3 text-[13px]">
                    <label className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={level !== undefined}
                        aria-label={t('connections.import.pick', { name: item.name })}
                        onChange={(e) => {
                          const next = { ...chosen }
                          if (e.target.checked) next[item.id] = { scope: 'general' }
                          else delete next[item.id]
                          setChosen(next)
                        }}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="font-mono font-medium">{item.name}</span>
                        <span className="ml-2 text-muted-foreground">{item.origin}</span>
                        {item.imported && (
                          <span className="ml-2 rounded bg-subtle px-1.5 text-[11.5px]">
                            {t('connections.import.already')}
                          </span>
                        )}
                        <span className="block truncate font-mono text-[12px] text-muted-foreground">
                          {item.target}
                        </span>
                        {item.has_secrets && (
                          <span className="block text-[12px]">
                            {t('connections.import.secrets')}
                          </span>
                        )}
                        {item.ignored.length > 0 && (
                          <span className="block text-[12px] text-muted-foreground">
                            {t('connections.paste.ignored', { fields: item.ignored.join(', ') })}
                          </span>
                        )}
                      </span>
                    </label>
                    {level !== undefined && (
                      <LevelSelect
                        value={level}
                        label={t('connections.import.levelOf', { name: item.name })}
                        onChange={(next) => setChosen({ ...chosen, [item.id]: next })}
                      />
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          {error && (
            <p role="alert" className="text-[13px] text-status-failed">
              {error}
            </p>
          )}
          <div className="mt-auto flex justify-end gap-2 border-t pt-3">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="button" disabled={ids.length === 0 || run.isPending} onClick={submit}>
              {t('connections.import.action', { count: ids.length })}
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
