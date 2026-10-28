export const CONTACT_EMAIL = 'contacto@cafeconpalito.com'

/**
 * The `mailto:` of «Informar de un error» (phase 20): the subject names the version, and the
 * body has the versions, the system and a short template. Spike S3: a body of ~1.6 KB reached
 * the mail program whole; this one stays well under that.
 */
export function bugReportHref({
  version,
  backendVersion,
  system = typeof navigator === 'undefined' ? '' : navigator.userAgent,
  texts,
}: {
  version: string
  backendVersion?: string
  system?: string
  texts: { subject: string; doing: string; expected: string; happened: string; logs: string }
}): string {
  const lines = [
    `Agentic OS ${version}${backendVersion && backendVersion !== version ? ` · backend ${backendVersion}` : ''}`,
    system,
    '',
    texts.doing,
    '',
    '',
    texts.expected,
    '',
    '',
    texts.happened,
    '',
    '',
    texts.logs,
  ]
  const subject = encodeURIComponent(`${texts.subject} · Agentic OS ${version}`)
  const body = encodeURIComponent(lines.join('\n'))
  return `mailto:${CONTACT_EMAIL}?subject=${subject}&body=${body}`
}
