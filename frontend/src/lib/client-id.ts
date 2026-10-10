let tabId: string | null = null

function randomId(): string {
  return crypto.randomUUID().replace(/-/g, '').slice(0, 12)
}

/** Stable id of this window/tab (survives reloads). */
function getTabId(): string {
  if (tabId) return tabId
  try {
    tabId = sessionStorage.getItem('agentic-os.tab-id')
    if (!tabId) {
      tabId = randomId()
      sessionStorage.setItem('agentic-os.tab-id', tabId)
    }
  } catch {
    tabId = randomId()
  }
  return tabId
}

/**
 * Id of one terminal view. Each view (run page, dock tab…) is a separate viewer on the
 * backend, and only the view that took the control can type.
 */
export function newViewerId(): string {
  return `${getTabId()}-${randomId().slice(0, 6)}`
}
