import { Copy, GitBranch } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useGenerateKey,
  useGlobalConfig,
  useSaveToken,
  useSetGlobalConfig,
  useSshKeys,
  useTestConnection,
  useTokenState,
} from '@/api/forges'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/form-errors'
import { gitErrorText } from '@/pages/projects/tabs/git/git-errors'

const HOSTS = ['github.com', 'gitlab.com']

/** «Git» (phase 12): the identity and defaults every repository inherits, SSH keys and the
 * tokens of the code hosts. Nothing here is stored by the app: it is git's own configuration,
 * `~/.ssh` and git's credential store. */
export function GitSection() {
  const { t } = useTranslation()
  return (
    <section
      aria-labelledby="git-title"
      className="flex flex-col gap-5 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <h2 id="git-title" className="flex items-center gap-2 text-[15px] font-medium">
        <GitBranch className="size-4" />
        {t('settings.git.title')}
      </h2>
      <GlobalConfig />
      <SshKeys />
      <Accounts />
    </section>
  )
}

function GlobalConfig() {
  const { t } = useTranslation()
  const config = useGlobalConfig()
  const set = useSetGlobalConfig()
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  async function save(key: string, value: string) {
    try {
      await set.mutateAsync({ key, value: value.trim() === '' ? null : value.trim() })
      setDrafts((current) => Object.fromEntries(Object.entries(current).filter(([k]) => k !== key)))
      toast.success(t('git.settings.saved', { key }))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[13px] font-medium">{t('settings.git.global')}</h3>
      <p className="text-xs text-muted-foreground">{t('settings.git.globalHelp')}</p>
      {Object.entries(config.data ?? {}).map(([key, values]) => {
        const current = values.global ?? ''
        const draft = drafts[key]
        return (
          <form
            key={key}
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              void save(key, draft ?? current)
            }}
          >
            <span className="w-44 font-mono text-xs">{key}</span>
            <Input
              value={draft ?? current}
              onChange={(e) => setDrafts({ ...drafts, [key]: e.target.value })}
              aria-label={key}
              className="h-8 w-64 text-xs"
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
  )
}

function SshKeys() {
  const { t } = useTranslation()
  const keys = useSshKeys()
  const generate = useGenerateKey()
  const test = useTestConnection()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('id_ed25519_agentic')
  const [email, setEmail] = useState('')
  const [passphrase, setPassphrase] = useState('')
  const [results, setResults] = useState<Record<string, string>>({})

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(t('settings.git.copied'))
    } catch {
      toast.error(t('settings.git.copyFailed'))
    }
  }

  async function onTest(host: string) {
    try {
      const result = await test.mutateAsync({ host })
      setResults((current) => ({
        ...current,
        [host]: result.ok
          ? t('settings.git.connected', { user: result.user ?? '' })
          : t('settings.git.notConnected', { message: result.message }),
      }))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[13px] font-medium">{t('settings.git.keys')}</h3>
      {(keys.data ?? []).length === 0 && (
        <p className="text-xs text-muted-foreground">{t('settings.git.noKeys')}</p>
      )}
      <ul className="flex flex-col gap-1.5">
        {(keys.data ?? []).map((key) => (
          <li key={key.name} className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className="font-mono">{key.name}</span>
            <Badge variant="secondary">{key.type.replace('ssh-', '')}</Badge>
            {key.orphan && <Badge variant="outline">{t('settings.git.orphan')}</Badge>}
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
              {key.fingerprint} {key.comment}
            </span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              aria-label={`${t('settings.git.copy')} ${key.name}`}
              onClick={() => void copy(key.public)}
            >
              <Copy />
              {t('settings.git.copy')}
            </Button>
          </li>
        ))}
      </ul>

      {creating ? (
        <form
          aria-label={t('settings.git.generate')}
          className="flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            void generate
              .mutateAsync({ name: name.trim(), email: email.trim(), passphrase })
              .then(() => {
                setCreating(false)
                setPassphrase('')
                toast.success(t('settings.git.generated', { name }))
              })
              .catch((error: unknown) => toast.error(gitErrorText(error, t)))
          }}
        >
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label={t('settings.git.keyName')}
            className="h-8 w-48 font-mono text-xs"
          />
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t('settings.git.email')}
            aria-label={t('settings.git.email')}
            className="h-8 w-56 text-xs"
          />
          <Input
            type="password"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            placeholder={t('settings.git.passphrase')}
            aria-label={t('settings.git.passphrase')}
            className="h-8 w-48 text-xs"
          />
          <Button type="submit" size="sm" disabled={!name.trim() || !email.trim()}>
            {t('settings.git.generateSubmit')}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setCreating(false)}>
            {t('common.cancel')}
          </Button>
        </form>
      ) : (
        <div>
          <Button type="button" size="sm" variant="outline" onClick={() => setCreating(true)}>
            {t('settings.git.generate')}
          </Button>
        </div>
      )}

      <div className="flex flex-col gap-1">
        <h4 className="text-xs text-muted-foreground">{t('settings.git.testTitle')}</h4>
        {HOSTS.map((host) => (
          <div key={host} className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className="w-28 font-mono text-xs">{host}</span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              aria-label={`${t('settings.git.test')} ${host}`}
              disabled={test.isPending}
              onClick={() => void onTest(host)}
            >
              {t('settings.git.test')}
            </Button>
            {results[host] && (
              <span role="status" className="text-xs text-muted-foreground">
                {results[host]}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function Accounts() {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[13px] font-medium">{t('settings.git.accounts')}</h3>
      <p className="text-xs text-muted-foreground">{t('settings.git.accountsHelp')}</p>
      {HOSTS.map((host) => (
        <HostToken key={host} host={host} />
      ))}
    </div>
  )
}

function HostToken({ host }: { host: string }) {
  const { t } = useTranslation()
  const state = useTokenState(host)
  const save = useSaveToken()
  const [token, setToken] = useState('')

  return (
    <form
      aria-label={host}
      className="flex flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        void save
          .mutateAsync({ host, token })
          .then(() => {
            setToken('')
            toast.success(t('git.pulls.tokenSaved', { host }))
          })
          .catch((error: unknown) => toast.error(errorMessage(error)))
      }}
    >
      <span className="w-28 font-mono text-xs">{host}</span>
      <Badge variant={state.data?.has_token ? 'secondary' : 'outline'}>
        {state.data?.has_token ? t('settings.git.hasToken') : t('settings.git.noToken')}
      </Badge>
      <Input
        type="password"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        placeholder={t('git.pulls.token')}
        aria-label={`${t('git.pulls.token')} ${host}`}
        className="h-8 w-64 font-mono text-xs"
      />
      <Button type="submit" size="sm" disabled={!token.trim() || save.isPending}>
        {t('git.pulls.saveToken')}
      </Button>
    </form>
  )
}
