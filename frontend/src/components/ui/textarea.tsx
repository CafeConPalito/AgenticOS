import * as React from 'react'
import { DictationButton } from '@/components/dictation/DictationButton'
import { cn } from '@/lib/utils'

type TextareaProps = React.ComponentProps<'textarea'> & {
  /** Adds the microphone: the text can be dictated into this field (phase 16). */
  dictation?: boolean
  /** Classes of the box that holds the field and its microphone. */
  containerClassName?: string
}

function Textarea({ className, dictation, containerClassName, ref, ...props }: TextareaProps) {
  const inner = React.useRef<HTMLTextAreaElement | null>(null)
  const setRef = React.useCallback(
    (node: HTMLTextAreaElement | null) => {
      inner.current = node
      if (typeof ref === 'function') ref(node)
      else if (ref) ref.current = node
    },
    [ref],
  )
  const field = (
    <textarea
      ref={setRef}
      data-slot="textarea"
      className={cn(
        'flex field-sizing-content min-h-16 w-full rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30 dark:aria-invalid:ring-destructive/40',
        dictation && 'pr-10',
        className,
      )}
      {...props}
    />
  )
  if (!dictation) return field
  return (
    <div className={cn('relative w-full', containerClassName)}>
      {field}
      <DictationButton target={inner} className="absolute top-1.5 right-1.5" />
    </div>
  )
}

export { Textarea }
