import type { ResolvedTheme } from '@/theme/model'

/** A tiny picture of a theme: its background, a card, a button and the status colors. */
export function ThemeSwatch({ theme }: { theme: ResolvedTheme }) {
  const c = theme.colors
  return (
    <div
      aria-hidden
      className="flex h-[84px] flex-col gap-1.5 overflow-hidden rounded-lg border p-2"
      style={{ background: c.background, borderColor: c.border }}
    >
      <div className="flex items-center gap-1.5">
        <span
          className="size-3 rounded-[4px]"
          style={{ background: `linear-gradient(145deg, ${c['logo-from']}, ${c['logo-to']})` }}
        />
        <span className="h-1.5 w-12 rounded-full" style={{ background: c.foreground }} />
        <span
          className="ml-auto h-3 w-7 rounded-full"
          style={{ background: c['primary-action'] }}
        />
      </div>
      <div
        className="flex flex-1 flex-col justify-center gap-1 rounded-md px-2"
        style={{ background: c.card, border: `1px solid ${c.border}` }}
      >
        <span className="h-1.5 w-16 rounded-full" style={{ background: c['card-foreground'] }} />
        <span className="h-1 w-10 rounded-full" style={{ background: c['muted-foreground'] }} />
        <div className="flex gap-1">
          {(['status-running', 'status-done', 'status-waiting', 'status-failed'] as const).map(
            (token) => (
              <span
                key={token}
                className="size-1.5 rounded-full"
                style={{ background: c[token] }}
              />
            ),
          )}
        </div>
      </div>
    </div>
  )
}
