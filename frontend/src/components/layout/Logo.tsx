export function Logo() {
  return (
    <span
      aria-hidden
      className="relative grid size-7 shrink-0 place-items-center rounded-lg bg-primary-action"
    >
      <span className="size-2.5 rounded-[3px] border-2 border-white" />
      <span className="absolute top-[5px] right-[5px] size-[5px] rounded-full bg-status-running" />
    </span>
  )
}
