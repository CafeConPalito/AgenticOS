export function Logo() {
  return (
    <span
      aria-hidden
      className="relative grid size-7 shrink-0 place-items-center rounded-[10px] bg-[linear-gradient(145deg,var(--logo-from),var(--logo-to))] shadow-[inset_0_0_0_1px_color-mix(in_oklch,white_14%,transparent),0_6px_18px_-6px_var(--logo-from)]"
    >
      <span className="size-2.5 rounded-[3px] border-2 border-white" />
      <span className="absolute top-[5px] right-[5px] size-[5px] rounded-full bg-logo-dot" />
    </span>
  )
}
