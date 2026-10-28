import { AlertTriangle, ImagePlus } from 'lucide-react'
import { useState } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'
import { toast } from 'sonner'
import { useUpdateAgent, useUploadAvatar } from '@/api/agents'
import { AvatarDialog } from '@/components/agentic/AvatarDialog'
import { AgentAvatar } from '@/components/agentic/primitives'
import { ColorPicker } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/form-errors'
import { contrastRatio } from '@/theme/contrast'
import { useTheme } from '@/theme/ThemeProvider'
import type { AgentFormValues } from '../agent-form'

const HEX = /^#[0-9a-fA-F]{6}$/
/** Under this, the agent's color barely stands out from the cards it sits on. */
const MIN_COLOR_CONTRAST = 1.4

/**
 * The agent's picture and color (phase 20). The picture applies at once (a photo has to be
 * uploaded anyway), so it is not part of «Guardar cambios»; the color still is.
 */
export function AvatarField() {
  const { t } = useTranslation()
  const { agentId = '' } = useParams()
  const { control, setValue } = useFormContext<AgentFormValues>()
  const [name, color, avatar] = useWatch<AgentFormValues, ['name', 'color', 'avatar']>({
    name: ['name', 'color', 'avatar'],
  })
  const update = useUpdateAgent(agentId)
  const upload = useUploadAvatar(agentId)
  const [open, setOpen] = useState(false)
  const { resolved } = useTheme()
  const faint = HEX.test(color) && contrastRatio(color, resolved.colors.card) < MIN_COLOR_CONTRAST

  // Already saved: the form takes the new value without marking it as a pending change.
  const keep = (value: string | null) => setValue('avatar', value, { shouldDirty: false })

  function pick(value: string | null) {
    update.mutate(
      { avatar: value },
      {
        onSuccess: (agent) => {
          keep(agent.avatar)
          toast.success(t('avatars.saved'))
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  async function uploadPhoto(crop: Blob) {
    const agent = await upload.mutateAsync(crop)
    keep(agent.avatar)
    toast.success(t('avatars.saved'))
    return agent.avatar
  }

  return (
    <div className="flex items-start gap-4">
      <AgentAvatar name={name || '?'} color={color} avatar={avatar} size={56} />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
            <ImagePlus />
            {t('avatars.change')}
          </Button>
          {avatar && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={update.isPending}
              onClick={() => pick(null)}
            >
              {t('avatars.remove')}
            </Button>
          )}
        </div>
        <Controller
          control={control}
          name="color"
          render={({ field }) => (
            <div className="flex flex-wrap items-center gap-3">
              <ColorPicker
                value={field.value}
                onChange={field.onChange}
                colorLabel={(c) => t('agents.fields.color', { color: c })}
              />
              <HexInput value={field.value} onChange={field.onChange} />
            </div>
          )}
        />
        {faint && (
          <p className="flex items-center gap-1.5 text-xs text-status-waiting">
            <AlertTriangle className="size-3.5" />
            {t('avatars.faintColor')}
          </p>
        )}
      </div>
      <AvatarDialog
        open={open}
        onOpenChange={setOpen}
        name={name || '?'}
        color={color}
        value={avatar}
        onPick={pick}
        uploadPhoto={uploadPhoto}
      />
    </div>
  )
}

function HexInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation()
  const [text, setText] = useState(value)
  const [shown, setShown] = useState(value)
  // A swatch picked meanwhile: show its value.
  if (shown !== value) {
    setShown(value)
    setText(value)
  }
  return (
    <Input
      aria-label={t('avatars.hex')}
      value={text}
      maxLength={7}
      aria-invalid={!HEX.test(text) || undefined}
      onChange={(e) => {
        setText(e.target.value)
        if (HEX.test(e.target.value)) onChange(e.target.value.toUpperCase())
      }}
      onBlur={() => setText(value)}
      className="h-8 w-[100px] font-mono text-[12.5px]"
    />
  )
}
