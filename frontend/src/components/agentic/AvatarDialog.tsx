import { ImageUp } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import Cropper from 'react-easy-crop'
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
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { OWLS } from '@/lib/avatars'
import { errorMessage } from '@/lib/form-errors'
import {
  type CropArea,
  checkPhoto,
  cropToBlob,
  MAX_PHOTO_SIDE,
  PHOTO_TYPES,
} from '@/lib/image-crop'
import { cn } from '@/lib/utils'
import { AgentAvatar } from './primitives'

type Tab = 'owls' | 'photo' | 'initials'

/**
 * Chooses an agent's picture (phase 20): an owl of the gallery, a photo framed here or the
 * initials. The photo is cropped in the browser; only the crop is handed to `uploadPhoto`,
 * and the file the person picked is let go when the dialog closes.
 */
export function AvatarDialog({
  open,
  onOpenChange,
  name,
  color,
  value,
  onPick,
  uploadPhoto,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  name: string
  color: string
  value: string | null
  /** An owl (`owl:<id>`) or null; the photo goes through `uploadPhoto`. */
  onPick: (avatar: string | null) => void
  /** Sends the crop and returns the agent's new `avatar` (`photo:<hash>`). */
  uploadPhoto: (crop: Blob) => Promise<string | null>
}) {
  const { t } = useTranslation()
  const a = 'avatars'
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[620px]">
        <DialogHeader>
          <DialogTitle>{t(`${a}.title`, { name })}</DialogTitle>
          <DialogDescription>{t(`${a}.description`)}</DialogDescription>
        </DialogHeader>
        {open && (
          <Picker
            name={name}
            color={color}
            value={value}
            onPick={(avatar) => {
              onPick(avatar)
              onOpenChange(false)
            }}
            uploadPhoto={async (crop) => {
              const avatar = await uploadPhoto(crop)
              onOpenChange(false)
              return avatar
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function Picker({
  name,
  color,
  value,
  onPick,
  uploadPhoto,
}: {
  name: string
  color: string
  value: string | null
  onPick: (avatar: string | null) => void
  uploadPhoto: (crop: Blob) => Promise<string | null>
}) {
  const { t } = useTranslation()
  const a = 'avatars'
  const [tab, setTab] = useState<Tab>(value?.startsWith('photo:') ? 'photo' : 'owls')
  return (
    <Tabs value={tab} onValueChange={(next) => setTab(next as Tab)}>
      <TabsList>
        <TabsTrigger value="owls">{t(`${a}.tabs.owls`)}</TabsTrigger>
        <TabsTrigger value="photo">{t(`${a}.tabs.photo`)}</TabsTrigger>
        <TabsTrigger value="initials">{t(`${a}.tabs.initials`)}</TabsTrigger>
      </TabsList>
      <TabsContent value="owls">
        <div
          role="radiogroup"
          aria-label={t(`${a}.tabs.owls`)}
          className="grid grid-cols-[repeat(auto-fill,minmax(84px,1fr))] gap-2 pt-2"
        >
          {OWLS.map((owl) => {
            const avatar = `owl:${owl.id}`
            const selected = value === avatar
            return (
              <button
                key={owl.id}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => onPick(avatar)}
                className={cn(
                  'flex flex-col items-center gap-1 rounded-lg border border-transparent p-2 text-[11.5px] hover:bg-accent',
                  selected && 'border-ring bg-accent',
                )}
              >
                <AgentAvatar name={name} color={color} avatar={avatar} size={56} label="" />
                {t(`${a}.owls.${owl.id}` as 'avatars.owls.plain')}
              </button>
            )
          })}
        </div>
      </TabsContent>
      <TabsContent value="photo">
        <PhotoTab color={color} uploadPhoto={uploadPhoto} />
      </TabsContent>
      <TabsContent value="initials">
        <div className="flex items-center gap-4 pt-3">
          <AgentAvatar name={name} color={color} avatar={null} size={64} />
          <p className="flex-1 text-[13px] text-muted-foreground">{t(`${a}.initialsHelp`)}</p>
          <Button onClick={() => onPick(null)}>{t(`${a}.useInitials`)}</Button>
        </div>
      </TabsContent>
    </Tabs>
  )
}

function PhotoTab({
  color,
  uploadPhoto,
}: {
  color: string
  uploadPhoto: (crop: Blob) => Promise<string | null>
}) {
  const { t } = useTranslation()
  const a = 'avatars.photo'
  const inputRef = useRef<HTMLInputElement>(null)
  // The picked file, held only in memory with an object URL for the cropper.
  const [picked, setPicked] = useState<{ file: File; url: string } | null>(null)
  const file = picked?.file ?? null
  const url = picked?.url ?? null
  const [crop, setCrop] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [area, setArea] = useState<CropArea | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Released when another photo is picked and when the dialog closes.
  useEffect(() => {
    if (!url) return
    return () => URL.revokeObjectURL(url)
  }, [url])

  async function choose(chosen: File | undefined) {
    setError(null)
    setPicked(null)
    if (!chosen) return
    const check = await checkPhoto(chosen)
    if (!check.ok) {
      setError(t(`${a}.${check.reason}`, { max: MAX_PHOTO_SIDE }))
      return
    }
    setCrop({ x: 0, y: 0 })
    setZoom(1)
    setPicked({ file: chosen, url: URL.createObjectURL(chosen) })
  }

  async function use() {
    if (!file || !area) return
    setBusy(true)
    setError(null)
    try {
      await uploadPhoto(await cropToBlob(file, area))
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 pt-2">
      <input
        ref={inputRef}
        type="file"
        accept={PHOTO_TYPES.join(',')}
        className="hidden"
        aria-label={t(`${a}.file`)}
        onChange={(e) => {
          void choose(e.target.files?.[0])
          e.target.value = ''
        }}
      />
      {url ? (
        <>
          <div
            className="relative h-[280px] overflow-hidden rounded-lg"
            style={{ background: color }}
          >
            <Cropper
              image={url}
              crop={crop}
              zoom={zoom}
              aspect={1}
              maxZoom={6}
              onCropChange={setCrop}
              onZoomChange={setZoom}
              onCropComplete={(_, pixels) => setArea(pixels)}
            />
          </div>
          <div className="flex items-center gap-3">
            <Label htmlFor="avatar-zoom" className="shrink-0">
              {t(`${a}.zoom`)}
            </Label>
            <input
              id="avatar-zoom"
              type="range"
              min={1}
              max={6}
              step={0.05}
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
              className="flex-1 accent-primary-action"
            />
          </div>
          <p className="text-xs text-muted-foreground">{t(`${a}.frameHelp`)}</p>
        </>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex h-[180px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-input text-[13px] text-muted-foreground hover:bg-accent"
        >
          <ImageUp className="size-6" />
          {t(`${a}.pick`)}
          <span className="text-xs">{t(`${a}.limits`, { max: MAX_PHOTO_SIDE })}</span>
        </button>
      )}
      {error && (
        <p role="alert" className="text-xs text-status-failed">
          {error}
        </p>
      )}
      <DialogFooter>
        {url && (
          <Button variant="outline" onClick={() => inputRef.current?.click()}>
            {t(`${a}.another`)}
          </Button>
        )}
        <Button
          disabled={!url || !area || busy}
          onClick={() => void use()}
          className="bg-primary-action text-white hover:bg-primary-action-hover"
        >
          {busy ? t(`${a}.saving`) : t(`${a}.use`)}
        </Button>
      </DialogFooter>
    </div>
  )
}
