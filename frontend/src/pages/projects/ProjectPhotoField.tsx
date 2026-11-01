import { ImagePlus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useUpdateProject, useUploadProjectAvatar } from '@/api/projects'
import type { Project } from '@/api/types'
import { AvatarDialog } from '@/components/agentic/AvatarDialog'
import { ProjectMark } from '@/components/agentic/primitives'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'

/**
 * The photo of a project (phase 24): framed with the same crop as an agent's, without owls.
 * Without a photo the project shows its initial on its color. Shared by the project settings
 * (`SavedProjectPhoto`, applied at once) and «Nuevo proyecto» (the crop waits until the project
 * exists).
 */
export function ProjectPhotoField({
  name,
  color,
  avatar,
  preview,
  busy,
  onUpload,
  onRemove,
}: {
  name: string
  color: string
  avatar: string | null
  /** A crop that is not uploaded yet (object URL). */
  preview?: string | null
  busy?: boolean
  onUpload: (crop: Blob) => Promise<void>
  onRemove: () => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const has = Boolean(avatar || preview)
  return (
    <div className="flex items-center gap-4">
      <ProjectMark name={name || '?'} color={color} avatar={avatar} src={preview} size={56} />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
          <ImagePlus />
          {t(has ? 'projects.photo.change' : 'projects.photo.add')}
        </Button>
        {has && (
          <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={onRemove}>
            {t('projects.photo.remove')}
          </Button>
        )}
      </div>
      <AvatarDialog
        open={open}
        onOpenChange={setOpen}
        name={name || '?'}
        color={color}
        value={avatar}
        photoOnly
        onPick={(value) => {
          if (value === null) onRemove()
        }}
        uploadPhoto={async (crop) => {
          await onUpload(crop)
          return null
        }}
      />
    </div>
  )
}

/** The photo field of an existing project: every change is saved at once. */
export function SavedProjectPhoto({ project }: { project: Project }) {
  const { t } = useTranslation()
  const update = useUpdateProject(project.id)
  const upload = useUploadProjectAvatar()
  return (
    <section aria-label={t('projects.photo.title')} className="flex flex-col gap-2">
      <h2 className="text-[13px] font-medium">{t('projects.photo.title')}</h2>
      <ProjectPhotoField
        name={project.name}
        color={project.color}
        avatar={project.avatar}
        busy={update.isPending || upload.isPending}
        onUpload={async (crop) => {
          await upload.mutateAsync({ id: project.id, crop })
          toast.success(t('projects.photo.saved'))
        }}
        onRemove={() =>
          update.mutate(
            { avatar: null },
            {
              onSuccess: () => toast.success(t('projects.photo.removed')),
              onError: (error) => toast.error(errorMessage(error)),
            },
          )
        }
      />
    </section>
  )
}
