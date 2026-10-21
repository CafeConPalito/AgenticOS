import { useTranslation } from 'react-i18next'
import type { KnowledgeGraph } from '@/api/knowledge'
import { cn } from '@/lib/utils'
import { KIND_ICON, LEVEL_COLOR } from './nodes'
import type { NodeKind } from './model'

const KINDS: NodeKind[] = ['file', 'url', 'image', 'agent', 'proposed', 'ghost']

/** What the shapes and lines mean, and the topics found. */
export function GraphLegend({ graph }: { graph: KnowledgeGraph }) {
  const { t } = useTranslation()
  return (
    <div className="grid gap-4 text-[12.5px] md:grid-cols-2">
      <section aria-label={t('knowledge.graph.legend.title')} className="flex flex-col gap-2">
        <h3 className="font-medium">{t('knowledge.graph.legend.title')}</h3>
        <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
          {KINDS.map((kind) => {
            const Icon = KIND_ICON[kind]
            return (
              <li key={kind} className="flex items-center gap-1.5">
                <span
                  className={cn(
                    'flex size-5 items-center justify-center rounded-full border-2 bg-card',
                    kind === 'proposed' && 'border-dashed',
                    kind === 'ghost' && 'border-dotted',
                  )}
                  style={{ borderColor: LEVEL_COLOR.general }}
                >
                  <Icon aria-hidden className="size-3 text-muted-foreground" />
                </span>
                {t(`knowledge.graph.legend.${kind === 'ghost' ? 'removed' : kind}`)}
              </li>
            )
          })}
        </ul>
        <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
          <li className="flex items-center gap-1.5">
            <svg aria-hidden width="28" height="8">
              <line x1="0" y1="4" x2="28" y2="4" stroke="currentColor" strokeWidth="1.6" />
            </svg>
            {t('knowledge.graph.legend.derived')}
          </li>
          <li className="flex items-center gap-1.5">
            <svg aria-hidden width="28" height="8">
              <line
                x1="0"
                y1="4"
                x2="28"
                y2="4"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeDasharray="5 5"
              />
            </svg>
            {t('knowledge.graph.legend.related')}
          </li>
        </ul>
        <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
          {(['general', 'project', 'agent'] as const).map((level) => (
            <li key={level} className="flex items-center gap-1.5">
              <span
                aria-hidden
                className="size-3 rounded-full border-2"
                style={{ borderColor: LEVEL_COLOR[level] }}
              />
              {t(`knowledge.graph.filters.${level}`)}
            </li>
          ))}
        </ul>
      </section>
      {graph.topics.length > 0 && (
        <section aria-label={t('knowledge.graph.topics.title')} className="flex flex-col gap-2">
          <h3 className="font-medium">{t('knowledge.graph.topics.title')}</h3>
          <ul className="flex flex-col gap-1">
            {graph.topics.map((topic) => (
              <li key={topic.id}>
                {topic.loose ? t('knowledge.graph.topics.loose') : topic.name}{' '}
                <span className="text-muted-foreground">
                  · {t('knowledge.graph.topics.docs', { count: topic.size })}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
