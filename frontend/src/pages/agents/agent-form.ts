import { z } from 'zod'
import i18n from '@/i18n'
import type { Agent, AgentFields } from '@/api/types'
import { MAX_CONCURRENCY, PERMISSION_MODES, TOOLS } from '@/api/types'

export function agentSchema() {
  return z.object({
    name: z.string().trim().min(1, i18n.t('errors.name_required')).max(80),
    role: z.string().trim().max(80),
    description: z.string(),
    color: z.string().regex(/^#[0-9A-Fa-f]{6}$/),
    cli: z.enum(['claude', 'agy']),
    model: z.string().trim().max(80),
    instructions: z.string(),
    permission_mode: z.enum(PERMISSION_MODES),
    allowed_tools: z.array(z.enum(TOOLS)),
    max_concurrency: z.number().int().min(1).max(MAX_CONCURRENCY),
    can_spawn_subagents: z.boolean(),
    can_create_tasks: z.boolean(),
    status: z.enum(['active', 'draft']),
    team_id: z.string().nullable(),
    account_id: z.string().nullable(),
    fallback_account_id: z.string().nullable(),
    fallback_model: z.string().trim().max(80),
  })
}

export type AgentFormValues = AgentFields

export const AGENT_FIELDS = [
  'name',
  'role',
  'description',
  'color',
  'cli',
  'model',
  'instructions',
  'permission_mode',
  'allowed_tools',
  'max_concurrency',
  'can_spawn_subagents',
  'can_create_tasks',
  'status',
  'team_id',
  'account_id',
  'fallback_account_id',
  'fallback_model',
] as const satisfies readonly (keyof AgentFields)[]

export function toFormValues(agent: Agent): AgentFormValues {
  return Object.fromEntries(AGENT_FIELDS.map((f) => [f, agent[f]])) as unknown as AgentFormValues
}

/** Only the fields the user changed, to send in the PATCH. */
export function changedFields(
  values: AgentFormValues,
  dirty: Partial<Record<keyof AgentFormValues, unknown>>,
): Partial<AgentFields> {
  return Object.fromEntries(
    AGENT_FIELDS.filter((f) => dirty[f]).map((f) => [f, values[f]]),
  ) as Partial<AgentFields>
}
