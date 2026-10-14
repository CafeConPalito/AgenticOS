import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { SHORTCUTS } from '@/lib/shortcuts'
import { Kbd } from './Kbd'

const GROUPS = ['general', 'create'] as const

/** The table of shortcuts (`?`), in two columns. */
export function ShortcutsDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[520px] gap-0 overflow-hidden p-0 sm:max-w-[520px]">
        <DialogHeader className="border-b border-sep px-4 py-3.5">
          <DialogTitle className="text-[15px] font-medium">{t('shortcuts.title')}</DialogTitle>
          <DialogDescription className="sr-only">{t('shortcuts.description')}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 px-4 pt-2 pb-4">
          {GROUPS.map((group) => (
            <div key={group} className="flex flex-col gap-0.5 pt-2">
              <div className="mb-1 text-[11.5px] text-muted-foreground">
                {t(`shortcuts.groups.${group}`)}
              </div>
              {SHORTCUTS.filter((s) => s.group === group).map((shortcut) => (
                <div key={shortcut.id} className="flex h-7 items-center gap-2">
                  <span className="flex-1">{t(`shortcuts.${shortcut.label}`)}</span>
                  <Kbd keys={shortcut.keys} />
                </div>
              ))}
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
