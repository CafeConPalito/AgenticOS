import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Segmented } from '@/pages/usage/parts'
import type { Base, ThemeDefinition } from '@/theme/model'
import { freeId } from './theme-io'

/** «Nuevo tema» (phase 22): a theme made from scratch, over the light or the dark base set. */
export function NewThemeDialog({
  open,
  onOpenChange,
  taken,
  defaultBase,
  onCreate,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Ids of the person's themes, for a free one. */
  taken: string[]
  defaultBase: Base
  onCreate: (theme: ThemeDefinition) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <NewThemeForm taken={taken} defaultBase={defaultBase} onCreate={onCreate} />}
    </Dialog>
  )
}

function NewThemeForm({
  taken,
  defaultBase,
  onCreate,
}: {
  taken: string[]
  defaultBase: Base
  onCreate: (theme: ThemeDefinition) => void
}) {
  const { t } = useTranslation()
  const c = 'appearance.create'
  const [name, setName] = useState('')
  const [base, setBase] = useState<Base>(defaultBase)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    onCreate({
      format: 'agentic-os.theme',
      version: 2,
      id: freeId(trimmed, taken),
      name: trimmed,
      base,
      colors: {},
    })
  }

  return (
    <DialogContent className="sm:max-w-md">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <DialogHeader>
          <DialogTitle>{t(`${c}.title`)}</DialogTitle>
          <DialogDescription>{t(`${c}.description`)}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-theme-name">{t(`${c}.name`)}</Label>
          <Input
            id="new-theme-name"
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">{t(`${c}.base`)}</span>
          <div className="self-start">
            <Segmented<Base>
              label={t(`${c}.base`)}
              value={base}
              onChange={setBase}
              options={(['light', 'dark'] as const).map((value) => ({
                value,
                label: t(`appearance.editor.bases.${value}`),
              }))}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            type="submit"
            disabled={!name.trim()}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t(`${c}.submit`)}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}
