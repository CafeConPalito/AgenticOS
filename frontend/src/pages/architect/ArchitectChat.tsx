import {
  ArrowUp,
  LockOpen,
  MoreHorizontal,
  RotateCcw,
  Sparkles,
  Square,
  SquareTerminal,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router'
import remarkGfm from 'remark-gfm'
import { toast } from 'sonner'
import { type ArchitectMessage, type Conversation, useConversationActions } from '@/api/architect'
import { StatusBadge, type StatusTone } from '@/components/agentic/primitives'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'

const STATE_TONE: Record<Conversation['state'], StatusTone> = {
  starting: 'queued',
  thinking: 'running',
  idle: 'done',
  asleep: 'cancelled',
}

const MARKDOWN =
  'text-[13.5px] leading-relaxed [&_h1]:font-semibold [&_h2]:font-semibold [&_li]:ml-4 [&_ol]:list-decimal [&_p+p]:mt-2 [&_pre]:overflow-auto [&_pre]:rounded [&_pre]:bg-muted [&_pre]:p-2 [&_ul]:list-disc [&_code]:font-mono [&_code]:text-[12.5px]'

/** The conversation with the Architect (design §11, left half). */
export function ArchitectChat({
  conversation,
  blocks,
}: {
  conversation: Conversation
  blocks: string[]
}) {
  const { t } = useTranslation()
  const actions = useConversationActions(conversation.id)
  const [text, setText] = useState('')
  const bottom = useRef<HTMLDivElement>(null)
  const thinking = conversation.state === 'thinking' || conversation.state === 'starting'
  const closed = conversation.status === 'applied' || conversation.status === 'discarded'

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: 'end' })
  }, [conversation.messages.length, blocks.length])

  async function send() {
    const message = text.trim()
    if (!message || actions.send.isPending) return
    try {
      await actions.send.mutateAsync(message)
      setText('')
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function reset(clearSheet: boolean) {
    try {
      await actions.reset.mutateAsync(clearSheet)
      toast.success(t('architect.resetDone'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const locked = new Set(conversation.sheet.locked)

  return (
    <section className="flex min-h-0 flex-col border-r border-sep" aria-label={t('architect.chat')}>
      <header className="flex items-center gap-3 border-b border-sep px-5 py-3">
        <span
          aria-hidden
          className="flex size-9 items-center justify-center rounded-full text-white"
          style={{ background: 'var(--status-review)' }}
        >
          <Sparkles className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-medium">{conversation.title || t('architect.name')}</h1>
          <p className="truncate text-[12.5px] text-muted-foreground">
            {t(`architect.modes.${conversation.mode}`)}
          </p>
        </div>
        <StatusBadge
          tone={STATE_TONE[conversation.state]}
          label={t(`architect.state.${conversation.state}`)}
          size="xs"
        />
        {conversation.run_id && (
          <Button variant="ghost" size="sm" asChild>
            <Link to={`/ejecuciones/${conversation.run_id}`}>
              <SquareTerminal />
              {t('architect.terminal')}
            </Link>
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={t('common.more')}>
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => void reset(false)}>
              <RotateCcw />
              {t('architect.reset')}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void reset(true)}>
              <RotateCcw />
              {t('architect.resetAndClear')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {conversation.messages.length === 0 && !thinking && (
          <Bubble from="architect">
            <p>
              {t(
                conversation.mode === 'improve_agent'
                  ? 'architect.helloImprove'
                  : 'architect.hello',
              )}
            </p>
          </Bubble>
        )}
        <ol className="flex flex-col gap-3">
          {conversation.messages.map((message) => (
            <li key={message.id}>
              <Message
                message={message}
                locked={locked}
                onUnlock={(field) => actions.unlock.mutate([field])}
              />
            </li>
          ))}
          {thinking && (
            <li>
              <Bubble from="architect">
                {blocks.length > 0 ? (
                  <div className={MARKDOWN}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{blocks.join('\n\n')}</ReactMarkdown>
                  </div>
                ) : null}
                <p className="mt-1 animate-pulse text-[12.5px] text-muted-foreground">
                  {t(
                    conversation.state === 'starting' ? 'architect.starting' : 'architect.thinking',
                  )}
                </p>
              </Bubble>
            </li>
          )}
        </ol>
        <div ref={bottom} />
      </div>

      <form
        className="border-t border-sep px-5 py-3"
        onSubmit={(event) => {
          event.preventDefault()
          void send()
        }}
      >
        <div className="flex items-end gap-2">
          <Textarea
            dictation
            rows={2}
            value={text}
            disabled={closed}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void send()
              }
            }}
            placeholder={t(closed ? 'architect.closed' : 'architect.placeholder')}
            aria-label={t('architect.messageLabel')}
            className="max-h-48 resize-none"
          />
          {thinking ? (
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label={t('architect.stop')}
              onClick={() => actions.interrupt.mutate()}
            >
              <Square />
            </Button>
          ) : null}
          <Button
            type="submit"
            size="icon"
            aria-label={t('architect.send')}
            disabled={closed || !text.trim() || actions.send.isPending}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <ArrowUp />
          </Button>
        </div>
        <p className="mt-1.5 text-[11.5px] text-muted-foreground">{t('architect.composerHint')}</p>
      </form>
    </section>
  )
}

function Bubble({ from, children }: { from: ArchitectMessage['role']; children: React.ReactNode }) {
  if (from === 'user')
    return (
      <div className="ml-auto max-w-[78%] rounded-xl bg-primary-action px-3.5 py-2.5 whitespace-pre-wrap text-white">
        {children}
      </div>
    )
  return (
    <div className="flex max-w-[78%] gap-2.5">
      <span
        aria-hidden
        className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white"
        style={{ background: 'var(--status-review)' }}
      >
        A
      </span>
      <div className="min-w-0 rounded-xl border border-sep bg-card px-3.5 py-2.5">{children}</div>
    </div>
  )
}

function Message({
  message,
  locked,
  onUnlock,
}: {
  message: ArchitectMessage
  locked: Set<string>
  onUnlock: (field: string) => void
}) {
  const { t } = useTranslation()
  if (message.role === 'system') {
    const unlock = message.tool_events.find((e) => e.unlock_request)?.unlock_request
    return (
      <div className="mx-auto flex max-w-[85%] flex-col items-center gap-2 text-center text-[12.5px] text-muted-foreground">
        <p className="whitespace-pre-wrap">{message.text}</p>
        {unlock && locked.has(unlock) && (
          <Button size="sm" variant="outline" onClick={() => onUnlock(unlock)}>
            <LockOpen />
            {t('architect.allowChange', { field: fieldLabel(t, unlock) })}
          </Button>
        )}
      </div>
    )
  }
  if (message.role === 'user') return <Bubble from="user">{message.text}</Bubble>
  const changed = message.tool_events.flatMap((e) => e.fields ?? [])
  return (
    <Bubble from="architect">
      <div className={MARKDOWN}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
      </div>
      {changed.length > 0 && (
        <p className={cn('mt-2 text-[12px] text-muted-foreground')}>
          {t('architect.changed', {
            fields: [...new Set(changed.map((f) => fieldLabel(t, f)))].join(', '),
          })}
        </p>
      )}
    </Bubble>
  )
}

/** «main.role» → «rol» (the field's name in the sheet). */
export function fieldLabel(t: TFunction, path: string): string {
  const field = path.split('.').pop() ?? path
  return t(`architect.fields.${field}` as never, { defaultValue: field })
}
