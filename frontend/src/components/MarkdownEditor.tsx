import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

/** Markdown textarea with an Edit / Preview toggle. */
export function MarkdownEditor({
  id,
  value,
  onChange,
  placeholder,
  minRows = 16,
  className,
}: {
  id?: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  minRows?: number
  className?: string
}) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'edit' | 'preview'>('edit')

  return (
    <div className={cn('flex flex-col overflow-hidden rounded-lg border bg-card', className)}>
      <div role="tablist" className="flex gap-1 border-b bg-subtle px-2 py-1.5">
        {(['edit', 'preview'] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            onClick={() => setMode(m)}
            className={cn(
              'rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent',
              mode === m && 'bg-accent font-medium text-foreground',
            )}
          >
            {t(`markdown.${m}`)}
          </button>
        ))}
      </div>
      {mode === 'edit' ? (
        <Textarea
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={minRows}
          className="field-sizing-fixed min-h-0 resize-y rounded-none border-0 bg-transparent font-mono text-[13px] leading-[1.6] shadow-none focus-visible:ring-0"
        />
      ) : (
        <div className="markdown-preview min-h-[200px] px-4 py-3 text-[13px] leading-[1.6]">
          {value.trim() ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
          ) : (
            <p className="text-muted-foreground">{t('markdown.empty')}</p>
          )}
        </div>
      )}
    </div>
  )
}
