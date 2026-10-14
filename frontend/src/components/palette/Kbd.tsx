/** Key caps: `['Ctrl', 'K']` renders two. */
export function Kbd({ keys }: { keys: string[] }) {
  return (
    <span className="flex gap-0.5">
      {keys.map((key) => (
        <kbd
          key={key}
          className="rounded-md border border-sep bg-card px-1.5 py-px font-mono text-[11px] text-muted-foreground"
        >
          {key}
        </kbd>
      ))}
    </span>
  )
}
