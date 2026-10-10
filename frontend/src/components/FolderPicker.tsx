import { isTauri } from '@tauri-apps/api/core'
import { FolderOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

/** Folder path field: native folder dialog in the desktop app, plain text in the browser. */
export function FolderPicker({
  id,
  value,
  onChange,
  invalid,
}: {
  id?: string
  value: string
  onChange: (path: string) => void
  invalid?: boolean
}) {
  const { t } = useTranslation()
  const desktop = isTauri()

  async function browse() {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({
      directory: true,
      multiple: false,
      defaultPath: value || undefined,
      title: t('folderPicker.dialogTitle'),
    })
    if (typeof selected === 'string') onChange(selected)
  }

  return (
    <div className="flex gap-2">
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t('folderPicker.placeholder')}
        aria-invalid={invalid || undefined}
        className="font-mono text-[12.5px]"
      />
      {desktop && (
        <Button type="button" variant="outline" onClick={() => void browse()}>
          <FolderOpen />
          {t('folderPicker.browse')}
        </Button>
      )}
    </div>
  )
}
