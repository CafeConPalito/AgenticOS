import { KeyRound, LoaderCircle } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type Connection,
  cancelOAuthFlow,
  openOAuthPage,
  useConnectionSettings,
  useDisconnectOAuth,
  useOAuthFlow,
  useRefreshOAuth,
  useStartOAuth,
} from '@/api/connections'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { formatDateTime } from '@/lib/time'
import { connectionError } from './shared'

/**
 * The login of a remote server (OAuth): «Conectar» sends the person to the service in the
 * browser and takes them back here. The tokens stay in the credential store (CA8). A service
 * without dynamic registration needs the client id registered there with the address shown.
 */
export function OAuthPanel({ connection }: { connection: Connection }) {
  const { t } = useTranslation()
  const start = useStartOAuth()
  const disconnect = useDisconnectOAuth()
  const refresh = useRefreshOAuth()
  const settings = useConnectionSettings()
  const [flowId, setFlowId] = useState<string | null>(null)
  const flow = useOAuthFlow(flowId)
  const [own, setOwn] = useState(false)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [error, setError] = useState<string | null>(null)
  const status = connection.oauth?.status ?? 'disconnected'
  const waiting = ['starting', 'waiting'].includes(flow.data?.state ?? '')
  const returnAddress = `http://127.0.0.1:${settings.data?.oauth_port ?? 53682}/callback`

  async function connect() {
    setError(null)
    try {
      const started = await start.mutateAsync({
        id: connection.id,
        clientId: own ? clientId : undefined,
        clientSecret: own ? clientSecret : undefined,
      })
      setFlowId(started.id)
      if (started.state === 'waiting') await openOAuthPage(started.id)
      if (started.state === 'failed') setError(started.error)
    } catch (failed) {
      setError(connectionError(failed))
    }
  }

  async function renew() {
    setError(null)
    try {
      await refresh.mutateAsync(connection.id)
      toast.success(t('connections.oauth.renewed'))
    } catch (failed) {
      setError(connectionError(failed))
    }
  }

  const flowError = flow.data?.state === 'failed' ? flow.data.error : null
  return (
    <section
      aria-label={t('connections.oauth.title')}
      className="grid gap-3 rounded-lg border p-3 text-[13px]"
    >
      <div className="flex items-center gap-2">
        <KeyRound className="size-4 text-muted-foreground" aria-hidden />
        <h3 className="font-medium">{t('connections.oauth.title')}</h3>
        <span
          className={
            status === 'connected'
              ? 'bg-status-completed/15 text-status-completed rounded px-1.5 text-[11.5px]'
              : 'rounded bg-status-waiting/15 px-1.5 text-[11.5px] text-status-waiting'
          }
        >
          {t(`connections.oauth.status_${status}`)}
        </span>
      </div>
      {connection.oauth?.account_label && status === 'connected' && (
        <p className="text-[12.5px] text-muted-foreground">
          {t('connections.oauth.account', { label: connection.oauth.account_label })}
          {connection.oauth.expires_at
            ? ` · ${t('connections.oauth.expires', { when: formatDateTime(connection.oauth.expires_at) })}`
            : ''}
        </p>
      )}
      {waiting ? (
        <div className="flex flex-wrap items-center gap-2">
          <LoaderCircle className="size-4 animate-spin" aria-hidden />
          <span role="status">{t('connections.oauth.waiting')}</span>
          {flow.data?.authorization_url && (
            <a
              href={flow.data.authorization_url}
              target="_blank"
              rel="noreferrer"
              className="text-[12.5px] underline"
            >
              {t('connections.oauth.openAgain')}
            </a>
          )}
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => flowId && void cancelOAuthFlow(flowId)}
          >
            {t('common.cancel')}
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" size="sm" onClick={connect} disabled={start.isPending}>
            {status === 'connected'
              ? t('connections.oauth.reconnect')
              : status === 'needs_reauth'
                ? t('connections.oauth.connectAgain')
                : t('connections.oauth.connect')}
          </Button>
          {status === 'connected' && (
            <>
              <Button type="button" size="sm" variant="outline" onClick={renew}>
                {t('connections.oauth.renew')}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => disconnect.mutate(connection.id)}
              >
                {t('connections.oauth.disconnect')}
              </Button>
            </>
          )}
        </div>
      )}
      <label className="flex items-center gap-2 text-[12.5px]">
        <input type="checkbox" checked={own} onChange={(e) => setOwn(e.target.checked)} />
        {t('connections.oauth.own')}
      </label>
      {own && (
        <div className="grid gap-2">
          <p className="text-[12px] text-muted-foreground">
            {t('connections.oauth.ownHint', { address: returnAddress })}
          </p>
          <div className="grid gap-1.5">
            <Label htmlFor="oauth-client-id">{t('connections.oauth.clientId')}</Label>
            <Input
              id="oauth-client-id"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="font-mono"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="oauth-client-secret">{t('connections.oauth.clientSecret')}</Label>
            <Input
              id="oauth-client-secret"
              type="password"
              autoComplete="off"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
            />
          </div>
        </div>
      )}
      {(error || flowError) && (
        <p role="alert" className="text-status-failed">
          {error ?? flowError}
        </p>
      )}
    </section>
  )
}
