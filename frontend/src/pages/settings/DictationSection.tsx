import { Mic, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useDictationSettings,
  useDictationStatus,
  useSaveDictationSettings,
  type DictationSettings,
} from '@/api/dictation'
import { useLocalModels } from '@/api/local-models'
import { Field } from '@/components/page'
import { Button } from '@/components/ui/button'
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
import { currentRecorder } from '@/lib/dictation/controller'
import { MicrophoneError } from '@/lib/dictation/recorder'
import { fromEvent, keycaps } from '@/lib/dictation/shortcut'
import { errorMessage } from '@/lib/form-errors'
import { useUiPrefs } from '@/stores/ui-prefs'
import { Kbd } from '@/components/palette/Kbd'

const LANGUAGES = ['es', 'en', 'ca', 'gl', 'eu', 'fr', 'de', 'it', 'pt'] as const
const DEFAULT_SHORTCUT = 'Ctrl+Space'
const TEST_SECONDS = 3
const SYSTEM_DEFAULT = '__default__'
/** A shortcut that would type something is not allowed: it needs Ctrl, Alt or Meta (Shift alone
 * types capitals; Ctrl+Alt is AltGr, which types symbols) or to be a function key. */
function isUsable(text: string): boolean {
  const parts = text.split('+')
  const keys = new Set(parts.slice(0, -1))
  if (/^F\d+$/.test(text)) return true
  if (keys.has('Ctrl') && keys.has('Alt')) return false
  return keys.has('Ctrl') || keys.has('Alt') || keys.has('Meta')
}

function ShortcutField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation()
  const [listening, setListening] = useState(false)
  const [rejected, setRejected] = useState(false)

  useEffect(() => {
    if (!listening) return
    function onKey(event: KeyboardEvent) {
      event.preventDefault()
      event.stopPropagation()
      if (event.key === 'Escape') {
        setListening(false)
        return
      }
      const pressed = fromEvent(event)
      if (!pressed) return // only modifiers so far
      if (!isUsable(pressed)) {
        setRejected(true)
        return
      }
      setRejected(false)
      setListening(false)
      onChange(pressed)
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [listening, onChange])

  return (
    <div className="flex flex-wrap items-center gap-2">
      {listening ? (
        <span className="rounded-md border border-ring px-2 py-1 text-[12.5px] text-muted-foreground">
          {t('settings.dictation.shortcutListening')}
        </span>
      ) : (
        <Kbd keys={keycaps(value, t('dictation.space'))} />
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => {
          setRejected(false)
          setListening((v) => !v)
        }}
      >
        {listening ? t('common.cancel') : t('settings.dictation.shortcutChange')}
      </Button>
      {value !== DEFAULT_SHORTCUT && !listening && (
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange(DEFAULT_SHORTCUT)}>
          {t('settings.dictation.shortcutReset')}
        </Button>
      )}
      {rejected && (
        <p role="alert" className="basis-full text-xs text-status-failed">
          {t('settings.dictation.shortcutInvalid')}
        </p>
      )}
    </div>
  )
}

function useMicrophones() {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  useEffect(() => {
    const media = navigator.mediaDevices
    if (!media?.enumerateDevices) return
    let alive = true
    const refresh = () =>
      void media
        .enumerateDevices()
        .then((all) => alive && setDevices(all.filter((d) => d.kind === 'audioinput')))
        .catch(() => undefined)
    refresh()
    media.addEventListener?.('devicechange', refresh)
    return () => {
      alive = false
      media.removeEventListener?.('devicechange', refresh)
    }
  }, [])
  return devices
}

function MicrophoneTest({ deviceId }: { deviceId: string | null }) {
  const { t } = useTranslation()
  const [state, setState] = useState<
    | { phase: 'idle' }
    | { phase: 'testing'; level: number; left: number }
    | { phase: 'done'; heard: boolean }
    | { phase: 'denied' }
  >({ phase: 'idle' })
  const peak = useRef(0)
  const last = useRef(0)

  async function run() {
    peak.current = 0
    last.current = 0
    try {
      const recording = await currentRecorder().start({
        deviceId: deviceId ?? undefined,
        onLevel: (level) => {
          peak.current = Math.max(peak.current, level)
          last.current = level
          setState((s) => (s.phase === 'testing' ? { ...s, level } : s))
        },
      })
      for (let left = TEST_SECONDS; left > 0; left--) {
        setState((s) => ({
          phase: 'testing',
          level: s.phase === 'testing' ? s.level : last.current,
          left,
        }))
        await new Promise((resolve) => setTimeout(resolve, 1000))
      }
      await recording.stop()
      setState({ phase: 'done', heard: peak.current > 0.05 })
    } catch (error) {
      if (error instanceof MicrophoneError && error.problem === 'permission')
        setState({ phase: 'denied' })
      else {
        setState({ phase: 'idle' })
        toast.error(
          t(`dictation.errors.${error instanceof MicrophoneError ? error.problem : 'failed'}`),
        )
      }
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={state.phase === 'testing'}
          onClick={() => void run()}
        >
          <Mic />
          {t('settings.dictation.microphoneTest')}
        </Button>
        {state.phase === 'testing' && (
          <>
            <span
              role="meter"
              aria-label={t('settings.dictation.microphone')}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(state.level * 100)}
              className="h-1.5 w-24 overflow-hidden rounded-full bg-muted"
            >
              <span
                className="block h-full rounded-full bg-primary-action transition-[width] duration-75"
                style={{ width: `${Math.round(state.level * 100)}%` }}
              />
            </span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {t('settings.dictation.microphoneTesting', { seconds: state.left })}
            </span>
          </>
        )}
      </div>
      {state.phase === 'done' && (
        <p role="status" className="text-xs text-muted-foreground">
          {t(
            state.heard ? 'settings.dictation.microphoneOk' : 'settings.dictation.microphoneSilent',
          )}
        </p>
      )}
      {state.phase === 'denied' && (
        <div role="alert" className="text-xs text-status-failed">
          <p>{t('settings.dictation.permission')}</p>
          <p className="text-muted-foreground">{t('settings.dictation.permissionHelp')}</p>
        </div>
      )}
    </div>
  )
}

function Vocabulary({ terms, onChange }: { terms: string[]; onChange: (terms: string[]) => void }) {
  const { t } = useTranslation()
  const [text, setText] = useState('')

  function add() {
    const term = text.trim().replace(/\s+/g, ' ')
    if (!term) return
    setText('')
    if (!terms.some((x) => x.toLowerCase() === term.toLowerCase())) onChange([...terms, term])
  }

  return (
    <div className="flex flex-col gap-2">
      <Input
        id="dictation-vocabulary"
        value={text}
        maxLength={60}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            add()
          }
        }}
        onBlur={add}
        placeholder={t('settings.dictation.vocabularyPlaceholder')}
      />
      {terms.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {terms.map((term) => (
            <li
              key={term}
              className="flex items-center gap-1 rounded-full border bg-subtle py-0.5 pr-1 pl-2.5 text-[12.5px]"
            >
              {term}
              <button
                type="button"
                aria-label={t('settings.dictation.vocabularyRemove', { term })}
                onClick={() => onChange(terms.filter((x) => x !== term))}
                className="rounded-full p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Form({ settings }: { settings: DictationSettings }) {
  const { t } = useTranslation()
  const save = useSaveDictationSettings()
  const status = useDictationStatus().data
  const models = useLocalModels().data?.models
  const devices = useMicrophones()
  const microphoneId = useUiPrefs((s) => s.microphoneId)
  const setMicrophoneId = useUiPrefs((s) => s.setMicrophoneId)
  const [seconds, setSeconds] = useState(String(settings.max_seconds))
  const speech = models?.filter((m) => m.kind === 'speech')
  const chosen = speech?.find((m) => m.selected) ?? speech?.find((m) => m.default)
  const usable = chosen?.state === 'ready'

  async function update(values: Partial<DictationSettings>) {
    try {
      await save.mutateAsync(values)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  function commitSeconds() {
    const value = Number(seconds)
    if (Number.isInteger(value) && value >= 30 && value <= 900) {
      if (value !== settings.max_seconds) void update({ max_seconds: value })
    } else {
      setSeconds(String(settings.max_seconds))
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <Label htmlFor="dictation-enabled">{t('settings.dictation.enabled')}</Label>
          <p className="text-xs text-muted-foreground">{t('settings.dictation.enabledHelp')}</p>
        </div>
        <Switch
          id="dictation-enabled"
          checked={settings.enabled}
          onCheckedChange={(enabled) => void update({ enabled })}
          aria-label={t('settings.dictation.enabled')}
        />
      </div>

      {status && (
        <p
          role="status"
          className={status.ready ? 'text-xs text-muted-foreground' : 'text-xs text-status-waiting'}
        >
          {t(`settings.dictation.status.${status.ready ? 'ready' : (status.reason ?? 'ready')}`)}
        </p>
      )}

      <Field
        label={t('settings.dictation.model')}
        htmlFor="dictation-model"
        help={t('settings.dictation.modelHelp')}
      >
        <div className="flex items-center gap-2" id="dictation-model">
          <span className="text-[13px]">
            {usable ? chosen.title : t('settings.dictation.modelNone')}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              document.getElementById('models')?.scrollIntoView({ behavior: 'smooth' })
            }
          >
            {t('settings.dictation.manageModels')}
          </Button>
        </div>
      </Field>

      <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
        <Field label={t('settings.dictation.language')} htmlFor="dictation-language">
          <Select value={settings.language} onValueChange={(language) => void update({ language })}>
            <SelectTrigger id="dictation-language" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">{t('settings.dictation.languageAuto')}</SelectItem>
              {LANGUAGES.map((code) => (
                <SelectItem key={code} value={code}>
                  {t(`settings.dictation.languages.${code}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field
          label={t('settings.dictation.maxSeconds')}
          htmlFor="dictation-seconds"
          help={t('settings.dictation.maxSecondsHelp', { seconds: settings.max_seconds })}
        >
          <Input
            id="dictation-seconds"
            type="number"
            min={30}
            max={900}
            value={seconds}
            onChange={(e) => setSeconds(e.target.value)}
            onBlur={commitSeconds}
          />
        </Field>
      </div>

      <Field label={t('settings.dictation.shortcut')} help={t('settings.dictation.shortcutHelp')}>
        <ShortcutField
          value={settings.shortcut}
          onChange={(shortcut) => void update({ shortcut })}
        />
      </Field>

      <Field label={t('settings.dictation.microphone')} htmlFor="dictation-microphone">
        <div className="flex flex-col gap-2">
          <Select
            value={microphoneId ?? SYSTEM_DEFAULT}
            onValueChange={(id) => setMicrophoneId(id === SYSTEM_DEFAULT ? null : id)}
          >
            <SelectTrigger id="dictation-microphone" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SYSTEM_DEFAULT}>
                {t('settings.dictation.microphoneDefault')}
              </SelectItem>
              {devices
                .filter((d) => d.deviceId && d.deviceId !== 'default')
                .map((device, index) => (
                  <SelectItem key={device.deviceId} value={device.deviceId}>
                    {device.label || `${t('settings.dictation.microphone')} ${index + 1}`}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <MicrophoneTest deviceId={microphoneId} />
        </div>
      </Field>

      <Field
        label={t('settings.dictation.vocabulary')}
        htmlFor="dictation-vocabulary"
        help={t('settings.dictation.vocabularyHelp')}
      >
        <Vocabulary
          terms={settings.vocabulary}
          onChange={(vocabulary) => void update({ vocabulary })}
        />
      </Field>
    </div>
  )
}

/** «Dictado por voz»: on or off, language, shortcut, microphone, limit and vocabulary. Each
 * change is saved as it is made. The model is chosen in «Modelos locales». */
export function DictationSection() {
  const { t } = useTranslation()
  const { data } = useDictationSettings()
  return (
    <section
      aria-labelledby="dictation-title"
      className="flex flex-col gap-4 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <div>
        <h2 id="dictation-title" className="text-[15px] font-medium">
          {t('settings.dictation.title')}
        </h2>
        <p className="mt-1 text-[12.5px] text-muted-foreground">
          {t('settings.dictation.description')}
        </p>
      </div>
      {data ? <Form settings={data} /> : <Skeleton aria-busy className="h-48 rounded-lg" />}
    </section>
  )
}
