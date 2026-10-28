import { FolderOpen } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useDataDir, useMoveDataDir, useOpenDataDir } from '@/api/settings'
import { FolderPicker } from '@/components/FolderPicker'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { resources } from '@/i18n'
import { errorMessage } from '@/lib/form-errors'
import { formatBytes } from '@/lib/format'
import { useUiPrefs } from '@/stores/ui-prefs'

const LANGUAGES = Object.keys(resources) as (keyof typeof resources)[]

/** «General» (design `12-ajustes`): data folder, language and shortcuts (the theme is in Apariencia). */
export function GeneralSection() {
  const { t, i18n } = useTranslation()
  const singleKey = useUiPrefs((s) => s.singleKeyShortcuts)
  const setSingleKey = useUiPrefs((s) => s.setSingleKeyShortcuts)
  return (
    <section
      aria-labelledby="general-title"
      className="flex flex-col gap-4 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <h2 id="general-title" className="text-[15px] font-medium">
        {t('settings.general.title')}
      </h2>
      <DataDirField />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="language">{t('settings.general.language')}</Label>
        <Select value={i18n.language} disabled={LANGUAGES.length < 2}>
          <SelectTrigger id="language" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LANGUAGES.map((code) => (
              <SelectItem key={code} value={code}>
                {t(`settings.general.languages.${code}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {LANGUAGES.length < 2 && (
          <p className="text-xs text-muted-foreground">{t('settings.general.languageHelp')}</p>
        )}
      </div>
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <Label htmlFor="single-key-shortcuts">{t('settings.general.singleKey')}</Label>
          <p className="text-xs text-muted-foreground">{t('settings.general.singleKeyHelp')}</p>
        </div>
        <Switch
          id="single-key-shortcuts"
          checked={singleKey}
          onCheckedChange={setSingleKey}
          aria-label={t('settings.general.singleKey')}
        />
      </div>
    </section>
  )
}

function DataDirField() {
  const { t } = useTranslation()
  const { data } = useDataDir()
  const open = useOpenDataDir()
  const [moving, setMoving] = useState(false)

  if (!data) return <Skeleton className="h-20 rounded-lg" />
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="data-dir">{t('settings.general.dataDir')}</Label>
      <div className="flex gap-2">
        <Input id="data-dir" readOnly value={data.path} className="font-mono text-[12.5px]" />
        <Button variant="outline" onClick={() => setMoving(true)}>
          {t('settings.general.change')}
        </Button>
      </div>
      <div className="flex items-center gap-3">
        <p className="flex-1 text-xs text-muted-foreground">
          {t('settings.general.dataDirHelp', { size: formatBytes(data.total_bytes) })}
          {data.knowledge_bytes + data.models_bytes > 0 &&
            ` · ${t('settings.general.dataDirKnowledge', {
              knowledge: formatBytes(data.knowledge_bytes),
              models: formatBytes(data.models_bytes),
            })}`}
        </p>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => open.mutate(undefined, { onError: (e) => toast.error(errorMessage(e)) })}
        >
          <FolderOpen />
          {t('settings.general.open')}
        </Button>
      </div>
      {data.last_error && (
        <p role="alert" className="text-[12.5px] text-status-failed">
          {t('settings.general.moveFailed', { error: data.last_error })}
        </p>
      )}
      <MoveDialog open={moving} onOpenChange={setMoving} />
    </div>
  )
}

function MoveDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const move = useMoveDataDir()
  const [target, setTarget] = useState('')

  function submit(e: React.FormEvent) {
    e.preventDefault()
    move.mutate(target.trim(), {
      onSuccess: (result) => {
        onOpenChange(false)
        toast.success(
          t(result.restarting ? 'settings.general.moving' : 'settings.general.moveManual'),
        )
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t('settings.general.moveTitle')}</DialogTitle>
            <DialogDescription>{t('settings.general.moveDescription')}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="data-dir-target">{t('settings.general.moveTarget')}</Label>
            <FolderPicker id="data-dir-target" value={target} onChange={setTarget} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={!target.trim() || move.isPending}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              {t('settings.general.moveConfirm')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
