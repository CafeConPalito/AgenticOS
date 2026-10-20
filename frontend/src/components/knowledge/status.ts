import type { DocStatus, KnowledgeDoc } from '@/api/knowledge'

export const WORKING: DocStatus[] = ['converting', 'images', 'describing', 'indexing']

/** Being processed now (not just waiting for its turn). */
export const isWorking = (doc: Pick<KnowledgeDoc, 'status'>) => WORKING.includes(doc.status)

export const isPending = (doc: Pick<KnowledgeDoc, 'status'>) =>
  doc.status === 'queued' || isWorking(doc)

/** 0–100 for the bar, or null when the step has no count (then it shows as «indeterminate»). */
export function progressPercent(doc: KnowledgeDoc): number | null {
  if (doc.progress_total <= 0) return null
  return Math.min(100, Math.round((doc.progress_done / doc.progress_total) * 100))
}
