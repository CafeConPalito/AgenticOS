import * as React from 'react'
import { DictationButton } from '@/components/dictation/DictationButton'
import { cn } from '@/lib/utils'

type InputProps = React.ComponentProps<'input'> & {
  /** Adds the microphone: the text can be dictated into this field (phase 16). */
  dictation?: boolean
  /** Classes of the box that holds the field and its microphone. */
  containerClassName?: string
}

function Input({ className, type, dictation, containerClassName, ref, ...props }: InputProps) {
  const inner = React.useRef<HTMLInputElement | null>(null)
  const setRef = React.useCallback(
    (node: HTMLInputElement | null) => {
      inner.current = node
      if (typeof ref === 'function') ref(node)
      else if (ref) ref.current = node
    },
    [ref],
  )
  const field = (
    <input
      ref={setRef}
      type={type}
      data-slot="input"
      className={cn(
        'h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-xs transition-[color,box-shadow] outline-none selection:bg-primary selection:text-primary-foreground file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm dark:bg-input/30',
        'focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50',
        'aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40',
        dictation && 'pr-10',
        className,
      )}
      {...props}
    />
  )
  if (!dictation) return field
  return (
    <div className={cn('relative min-w-0 flex-1', containerClassName)}>
      {field}
      <DictationButton target={inner} className="absolute top-1/2 right-1 -translate-y-1/2" />
    </div>
  )
}

export { Input }
