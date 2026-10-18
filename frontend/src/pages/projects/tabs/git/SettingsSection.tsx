import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { type ConfigScope, useRepoConfig, useSetConfig } from '@/api/git-more'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { gitErrorText } from './git-errors'

const SCOPES: ConfigScope[] = ['local', 'global']

/** The usual git settings (name, email, default branch, pull behaviour…), each with the value
 * of this repository and the global one. An empty value removes the setting from that scope. */
export function SettingsSection({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const config = useRepoConfig(repoId)
  const set = useSetConfig(repoId)
  // What was typed and not saved yet, by `scope:key`.
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  async function save(scope: ConfigScope, key: string, value: string) {
    try {
      await set.mutateAsync({ scope, key, value: value.trim() === '' ? null : value.trim() })
      setDrafts((current) =>
        Object.fromEntries(Object.entries(current).filter(([id]) => id !== `${scope}:${key}`)),
      )
      toast.success(t('git.settings.saved', { key }))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  if (config.isPending) return <Skeleton aria-busy className="m-6 h-40 rounded-lg" />

  return (
    <div className="flex flex-col gap-3 px-6 py-4">
      <p className="text-xs text-muted-foreground">{t('git.settings.help')}</p>
      <div className="overflow-hidden rounded-lg border border-sep bg-card">
        <div className="grid grid-cols-[minmax(10rem,1fr)_1fr_1fr] gap-3 border-b border-sep px-3 py-2 text-xs font-medium text-muted-foreground">
          <span>{t('git.settings.key')}</span>
          {SCOPES.map((scope) => (
            <span key={scope}>{t(`git.settings.scope.${scope}`)}</span>
          ))}
        </div>
        {Object.entries(config.data ?? {}).map(([key, values]) => (
          <div
            key={key}
            className="grid grid-cols-[minmax(10rem,1fr)_1fr_1fr] items-center gap-3 border-b border-sep px-3 py-1.5 text-[13px] last:border-b-0"
          >
            <span className="font-mono text-xs">{key}</span>
            {SCOPES.map((scope) => {
              const id = `${scope}:${key}`
              const current = values[scope] ?? ''
              const draft = drafts[id]
              return (
                <form
                  key={scope}
                  className="flex gap-1"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void save(scope, key, draft ?? current)
                  }}
                >
                  <Input
                    value={draft ?? current}
                    onChange={(e) => setDrafts({ ...drafts, [id]: e.target.value })}
                    aria-label={`${key} (${t(`git.settings.scope.${scope}`)})`}
                    className="h-7 text-xs"
                  />
                  {draft !== undefined && draft !== current && (
                    <Button type="submit" size="sm" disabled={set.isPending}>
                      {t('common.save')}
                    </Button>
                  )}
                </form>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
