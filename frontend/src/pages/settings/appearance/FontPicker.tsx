import { AlertTriangle, Check, ChevronsUpDown } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSearchBar,
} from '@/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { isFontMissing, useSystemFonts } from '@/lib/system-fonts'
import { FONT_FAMILY, FONTS, type Font } from '@/theme/model'
import { FONT_STACKS, fontStack } from '@/theme/apply'

export interface FontChoice {
  font: Font
  /** A font of the system, over `font`. */
  fontFamily: string | null
}

/**
 * The theme's font (phase 22): one of the four the app ships or any font of the system, with
 * a search, each name in its own font. Without a list (a browser with no access) the name is
 * typed. A font of the system missing on this machine is reported.
 */
export function FontPicker({
  id,
  value,
  onChange,
}: {
  id: string
  value: FontChoice
  onChange: (choice: FontChoice) => void
}) {
  const { t } = useTranslation()
  const f = 'appearance.editor.fonts'
  const [open, setOpen] = useState(false)
  // Read when the picker opens (in a browser it may ask for permission); kept afterwards.
  const fonts = useSystemFonts(open)
  const label = value.fontFamily ?? t(`${f}.${value.font}`)
  const missing = useMemo(
    () => value.fontFamily !== null && isFontMissing(value.fontFamily, fonts.data),
    [value.fontFamily, fonts.data],
  )

  function pick(choice: FontChoice) {
    onChange(choice)
    setOpen(false)
  }

  return (
    <div className="flex flex-col gap-1.5">
      <Button
        id={id}
        type="button"
        variant="outline"
        role="combobox"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className="w-[290px] max-w-full justify-between font-normal"
      >
        <span className="truncate" style={{ fontFamily: fontStack(value) }}>
          {label}
        </span>
        <ChevronsUpDown className="opacity-60" />
      </Button>
      {missing && (
        <p role="status" className="flex max-w-[290px] items-start gap-1.5 text-xs">
          <AlertTriangle className="mt-px size-3.5 shrink-0 text-status-waiting" />
          {t(`${f}.missing`, { name: value.fontFamily })}
        </p>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-md">
          <DialogTitle className="sr-only">{t(`${f}.title`)}</DialogTitle>
          <DialogDescription className="sr-only">{t(`${f}.description`)}</DialogDescription>
          <Command>
            <CommandSearchBar>
              <CommandInput placeholder={t(`${f}.search`)} />
            </CommandSearchBar>
            <CommandList className="max-h-[360px]">
              <CommandEmpty>{t(`${f}.none`)}</CommandEmpty>
              <CommandGroup heading={t(`${f}.included`)}>
                {FONTS.map((font) => (
                  <FontItem
                    key={font}
                    value={`included:${font}`}
                    name={t(`${f}.${font}`)}
                    stack={FONT_STACKS[font]}
                    selected={!value.fontFamily && value.font === font}
                    onSelect={() => pick({ font, fontFamily: null })}
                  />
                ))}
              </CommandGroup>
              {fonts.data && fonts.data.length > 0 && (
                <CommandGroup heading={t(`${f}.system`)}>
                  {fonts.data.map((family) => (
                    <FontItem
                      key={family}
                      value={`system:${family}`}
                      name={family}
                      stack={fontStack({ font: 'system', fontFamily: family })}
                      selected={value.fontFamily === family}
                      onSelect={() => pick({ font: value.font, fontFamily: family })}
                    />
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
          {fonts.isFetched && !fonts.data && (
            <TypedFont onUse={(family) => pick({ font: value.font, fontFamily: family })} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function FontItem({
  value,
  name,
  stack,
  selected,
  onSelect,
}: {
  /** Unique in the list: «Inter» ships with the app and may be installed too. */
  value: string
  name: string
  stack: string
  selected: boolean
  onSelect: () => void
}) {
  return (
    <CommandItem value={value} keywords={[name]} onSelect={onSelect}>
      <span className="min-w-0 flex-1 truncate" style={{ fontFamily: stack }}>
        {name}
      </span>
      {selected && <Check className="size-4" />}
    </CommandItem>
  )
}

/** Where the system's fonts cannot be listed: the name, typed. */
function TypedFont({ onUse }: { onUse: (family: string) => void }) {
  const { t } = useTranslation()
  const f = 'appearance.editor.fonts'
  const [name, setName] = useState('')
  const valid = FONT_FAMILY.test(name.trim())
  return (
    <form
      className="flex flex-col gap-1.5 border-t border-sep p-3"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) onUse(name.trim())
      }}
    >
      <label htmlFor="typed-font" className="text-xs text-muted-foreground">
        {t(`${f}.typed`)}
      </label>
      <div className="flex gap-2">
        <Input
          id="typed-font"
          value={name}
          maxLength={80}
          placeholder="Cascadia Code"
          onChange={(e) => setName(e.target.value)}
        />
        <Button type="submit" variant="outline" disabled={!valid}>
          {t(`${f}.use`)}
        </Button>
      </div>
    </form>
  )
}
