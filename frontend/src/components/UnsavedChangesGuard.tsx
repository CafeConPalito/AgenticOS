import { useEffect, type RefObject } from 'react'
import { useTranslation } from 'react-i18next'
import { useBlocker } from 'react-router'
import { ConfirmDialog } from './ConfirmDialog'

/**
 * Asks before leaving a page with unsaved changes: in-app navigation shows a dialog,
 * closing/reloading the window triggers the browser's native prompt.
 *
 * `allowRef` lets a page navigate away on purpose right after an action (e.g. delete)
 * without waiting for a re-render to clear `when`.
 */
export function UnsavedChangesGuard({
  when,
  allowRef,
  scope,
}: {
  when: boolean
  allowRef?: RefObject<boolean>
  /** Path prefix the edit lives under (e.g. `/agentes/<id>`): moving between its tabs is fine. */
  scope?: string
}) {
  const { t } = useTranslation()
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (!when || allowRef?.current) return false
    const next = nextLocation.pathname
    const staying = scope
      ? next === scope || next.startsWith(`${scope}/`)
      : next === currentLocation.pathname
    return !staying
  })

  useEffect(() => {
    if (!when) return
    const handler = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [when])

  return (
    <ConfirmDialog
      open={blocker.state === 'blocked'}
      onOpenChange={(open) => !open && blocker.state === 'blocked' && blocker.reset()}
      title={t('unsaved.title')}
      description={t('unsaved.description')}
      confirmLabel={t('unsaved.discard')}
      destructive
      onConfirm={() => blocker.state === 'blocked' && blocker.proceed()}
    />
  )
}
