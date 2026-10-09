import { z } from 'zod'
import i18n from '@/i18n'

export function projectSchema() {
  return z.object({
    name: z.string().trim().min(1, i18n.t('errors.name_required')).max(80),
    path: z.string().trim().min(1, i18n.t('common.required')),
    color: z.string().regex(/^#[0-9A-Fa-f]{6}$/),
    description: z.string(),
    workspace_mode: z.enum(['direct', 'worktree']),
  })
}

export type ProjectFormValues = z.infer<ReturnType<typeof projectSchema>>

export const PROJECT_FORM_FIELDS = [
  'name',
  'path',
  'color',
  'description',
  'workspace_mode',
] as const
