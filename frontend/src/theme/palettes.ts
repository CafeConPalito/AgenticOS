/**
 * Data colors (phase 20): colors a person picks for an agent or a project, or that stand for
 * one, not colors of the interface. They stay the same in every theme, and they are the only
 * fixed colors allowed outside `theme/` (see no-hardcoded-colors.test.ts).
 */

/** The suggested colors for agents and projects (they read on light and dark). */
export const AGENT_COLORS = [
  '#F27FB2',
  '#4FD1C5',
  '#B5E061',
  '#FFA06B',
  '#8FB4FF',
  '#C4A1FF',
  '#FF8A8A',
  '#F2C94C',
]

export const PROJECT_COLORS = ['#7C9CFF', '#4FD1C5', '#B5E061', '#FFA06B', '#F27FB2', '#C4A1FF']

/** A new agent before the person picks a color. */
export const DEFAULT_AGENT_COLOR = '#8FB4FF'
/** An agent the Architect is still drafting. */
export const DRAFT_AGENT_COLOR = '#B39CFF'
/** A task or lane without an agent, and the person in the project memory. */
export const NEUTRAL_COLOR = '#C9D4E8'
