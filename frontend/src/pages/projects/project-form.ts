import { z } from 'zod'
import i18n from '@/i18n'

export function projectSchema() {
  return z.object({
    name: z.string().trim().min(1, i18n.t('errors.name_required')).max(80),
    path: z.string().trim().min(1, i18n.t('common.required')),
    color: z.string().regex(/^#[0-9A-Fa-f]{6}$/),
    description: z.string(),
    workspace_mode: z.enum(['direct', 'worktree']),
    /** Worktree mode; empty: the folder's current branch. */
    base_branch: z.string().trim().max(120),
  })
}

export type ProjectFormValues = z.infer<ReturnType<typeof projectSchema>>

export const PROJECT_FORM_FIELDS = [
  'name',
  'path',
  'color',
  'description',
  'workspace_mode',
  'base_branch',
] as const

/** What the API expects: an empty base branch means "the current one" (null). */
export function toApiValues<T extends Partial<ProjectFormValues>>(values: T) {
  return 'base_branch' in values ? { ...values, base_branch: values.base_branch || null } : values
}
