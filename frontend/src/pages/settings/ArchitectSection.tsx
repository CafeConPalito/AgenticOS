import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAccounts } from '@/api/accounts'
import {
  type ArchitectSettings,
  useArchitectSettings,
  useSaveArchitectSettings,
} from '@/api/architect'
import { Field } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'

const AUTO = '__auto__' // Radix Select cannot use "" as an item value

function Form({ initial }: { initial: ArchitectSettings }) {
  const { t } = useTranslation()
  const save = useSaveArchitectSettings()
  const accounts = useAccounts().data ?? []
  const [draft, setDraft] = useState(initial)
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial)
  const usable = accounts.filter((a) => !draft.cli || a.cli === draft.cli)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      const saved = await save.mutateAsync({
        cli: draft.cli,
        account_id: draft.account_id,
        model: draft.model,
        instructions: draft.instructions,
        idle_minutes: draft.idle_minutes,
        max_live: draft.max_live,
      })
      setDraft(saved)
      toast.success(t('architect.settings.saved'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">{t('architect.settings.help')}</p>
      <div className="grid grid-cols-3 gap-4 max-md:grid-cols-1">
        <Field label={t('architect.settings.cli')} htmlFor="architect-cli">
          <Select
            value={draft.cli || AUTO}
            onValueChange={(value) =>
              setDraft((d) => ({
                ...d,
                cli: value === AUTO ? '' : (value as 'claude' | 'agy'),
                account_id: '',
              }))
            }
          >
            <SelectTrigger id="architect-cli">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={AUTO}>{t('architect.settings.cliAuto')}</SelectItem>
              <SelectItem value="claude">{t('cli.claude')}</SelectItem>
              <SelectItem value="agy">{t('cli.agy')}</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label={t('architect.settings.account')} htmlFor="architect-account">
          <Select
            value={draft.account_id || AUTO}
            onValueChange={(value) =>
              setDraft((d) => ({ ...d, account_id: value === AUTO ? '' : value }))
            }
          >
            <SelectTrigger id="architect-account">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={AUTO}>{t('architect.settings.accountDefault')}</SelectItem>
              {usable.map((account) => (
                <SelectItem key={account.id} value={account.id}>
                  {account.name} · {t(`cli.${account.cli}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field
          label={t('architect.settings.model')}
          htmlFor="architect-model"
          help={t('architect.settings.modelHelp')}
        >
          <Input
            id="architect-model"
            value={draft.model}
            placeholder="sonnet"
            onChange={(e) => setDraft((d) => ({ ...d, model: e.target.value }))}
          />
        </Field>
      </div>
      <div className="grid grid-cols-3 gap-4 max-md:grid-cols-1">
        <Field
          label={t('architect.settings.idle')}
          htmlFor="architect-idle"
          help={t('architect.settings.idleHelp')}
        >
          <Input
            id="architect-idle"
            type="number"
            min={1}
            max={240}
            value={draft.idle_minutes}
            onChange={(e) => setDraft((d) => ({ ...d, idle_minutes: Number(e.target.value) }))}
          />
        </Field>
        <Field
          label={t('architect.settings.maxLive')}
          htmlFor="architect-live"
          help={t('architect.settings.maxLiveHelp')}
        >
          <Input
            id="architect-live"
            type="number"
            min={1}
            max={5}
            value={draft.max_live}
            onChange={(e) => setDraft((d) => ({ ...d, max_live: Number(e.target.value) }))}
          />
        </Field>
      </div>
      <Field
        label={t('architect.settings.instructions')}
        htmlFor="architect-instructions"
        help={t('architect.settings.instructionsHelp')}
      >
        <Textarea
          id="architect-instructions"
          rows={12}
          className="font-mono text-[12.5px]"
          value={draft.instructions || draft.default_instructions}
          onChange={(e) =>
            setDraft((d) => ({
              ...d,
              instructions: e.target.value === d.default_instructions ? '' : e.target.value,
            }))
          }
        />
      </Field>
      <div className="flex gap-2">
        <Button
          type="submit"
          disabled={!dirty || save.isPending}
          className="bg-primary-action text-white hover:bg-primary-action-hover"
        >
          {save.isPending ? t('common.saving') : t('common.save')}
        </Button>
        {draft.instructions && (
          <Button
            type="button"
            variant="outline"
            onClick={() => setDraft((d) => ({ ...d, instructions: '' }))}
          >
            {t('architect.settings.restore')}
          </Button>
        )}
      </div>
    </form>
  )
}

/** «Arquitecto» (phase 19): the CLI it talks through, its instructions and its CLIs' lifetime. */
export function ArchitectSection() {
  const { t } = useTranslation()
  const { data } = useArchitectSettings()
  return (
    <section
      aria-labelledby="architect-title"
      className="flex flex-col gap-4 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <h2 id="architect-title" className="text-[15px] font-medium">
        {t('architect.settings.title')}
      </h2>
      {data ? <Form initial={data} /> : <Skeleton aria-busy className="h-40 rounded-lg" />}
    </section>
  )
}
