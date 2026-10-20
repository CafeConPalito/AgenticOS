import { isTauri } from '@tauri-apps/api/core'
import { FilePlus2, Globe, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAddFiles, useAddUrl, type KnowledgeLevel } from '@/api/knowledge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/form-errors'
import { listenForDroppedFiles, pickFiles } from '@/lib/native-files'
import { cn } from '@/lib/utils'

/**
 * Adds documents to a level: drag and drop (desktop), the native file dialog, a web address,
 * or — in the browser, which cannot give real paths — a path typed by hand.
 */
export function AddDocuments({ level }: { level: KnowledgeLevel }) {
  const { t } = useTranslation()
  const addFiles = useAddFiles(level)
  const addUrl = useAddUrl(level)
  const [hovering, setHovering] = useState(false)
  const [url, setUrl] = useState('')
  const [path, setPath] = useState('')
  const desktop = isTauri()
  async function submitFiles(paths: string[]) {
    try {
      const results = await addFiles.mutateAsync(paths)
      for (const item of results) {
        if (item.doc) continue
        toast.error(item.path, {
          description: t(`knowledge.errors.${item.error_code ?? 'unknown'}`, {
            defaultValue: item.message,
          }),
        })
      }
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  // The drop listener lives as long as the component: it always calls the latest closure.
  const latest = useRef(submitFiles)
  useEffect(() => {
    latest.current = submitFiles
  })

  useEffect(() => {
    if (!desktop) return
    let stop: (() => void) | undefined
    let cancelled = false
    void listenForDroppedFiles((paths) => void latest.current(paths), setHovering).then((fn) => {
      if (cancelled) fn()
      else stop = fn
    })
    return () => {
      cancelled = true
      stop?.()
    }
  }, [desktop])

  async function browse() {
    const paths = await pickFiles(t('knowledge.add.dialogTitle'))
    if (paths.length > 0) await submitFiles(paths)
  }

  async function onAddUrl(event: React.FormEvent) {
    event.preventDefault()
    if (!url.trim()) return
    try {
      await addUrl.mutateAsync(url.trim())
      setUrl('')
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function onAddPath(event: React.FormEvent) {
    event.preventDefault()
    if (!path.trim()) return
    await submitFiles([path.trim()])
    setPath('')
  }

  return (
    <div
      className={cn(
        'flex flex-col gap-3 rounded-lg border border-dashed border-input p-4 transition-colors',
        hovering && 'border-primary-action bg-accent',
      )}
    >
      <div className="flex items-center gap-3">
        <Upload aria-hidden className="size-5 text-muted-foreground" />
        <p className="flex-1 text-[13px] text-muted-foreground">
          {desktop ? t('knowledge.add.dropHint') : t('knowledge.add.pathHint')}
        </p>
        {desktop && (
          <Button type="button" variant="outline" size="sm" onClick={() => void browse()}>
            <FilePlus2 />
            {t('knowledge.add.browse')}
          </Button>
        )}
      </div>
      {!desktop && (
        <form onSubmit={(e) => void onAddPath(e)} className="flex gap-2">
          <Input
            aria-label={t('knowledge.add.pathLabel')}
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder={t('knowledge.add.pathPlaceholder')}
            className="font-mono text-[12.5px]"
          />
          <Button type="submit" variant="outline" disabled={!path.trim() || addFiles.isPending}>
            {t('knowledge.add.addFile')}
          </Button>
        </form>
      )}
      <form onSubmit={(e) => void onAddUrl(e)} className="flex gap-2">
        <Input
          aria-label={t('knowledge.add.urlLabel')}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder={t('knowledge.add.urlPlaceholder')}
        />
        <Button type="submit" variant="outline" disabled={!url.trim() || addUrl.isPending}>
          <Globe />
          {t('knowledge.add.addUrl')}
        </Button>
      </form>
    </div>
  )
}
