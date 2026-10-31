import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAccounts } from '@/api/accounts'
import { useClis } from '@/api/clis'
import { useProjects } from '@/api/projects'
import { useOpenTerminal } from '@/api/terminals'
import type { CliId, Run } from '@/api/types'
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
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { errorMessage } from '@/lib/form-errors'

type Place = 'project' | 'home' | 'other'

/** «Nuevo terminal» (phase 23): a CLI opened by hand, with an account and in any folder. */
export function NewTerminalDialog({
  open,
  onOpenChange,
  onOpened,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onOpened: (run: Run) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <NewTerminalForm onOpened={onOpened} />}
    </Dialog>
  )
}

function NewTerminalForm({ onOpened }: { onOpened: (run: Run) => void }) {
  const { t } = useTranslation()
  const n = 'dock.new'
  const clis = (useClis().data ?? []).filter((cli) => cli.installed)
  const accounts = useAccounts().data ?? []
  const projects = useProjects().data ?? []
  const openTerminal = useOpenTerminal()
  const [cli, setCli] = useState<CliId | null>(null)
  const [accountId, setAccountId] = useState<string | null>(null)
  const [place, setPlace] = useState<Place>('home')
  const [projectId, setProjectId] = useState<string | null>(null)
  const [folder, setFolder] = useState('')

  const chosenCli = cli ?? clis[0]?.id ?? null
  const ofCli = accounts.filter((account) => account.cli === chosenCli)
  const account =
    ofCli.find((a) => a.id === accountId) ?? ofCli.find((a) => a.is_default) ?? ofCli[0]
  const project = projects.find((p) => p.id === projectId) ?? projects[0]
  const cwd = place === 'home' ? '~' : place === 'project' ? (project?.path ?? '') : folder.trim()

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!chosenCli || !cwd) return
    try {
      const run = await openTerminal.mutateAsync({
        cli: chosenCli,
        account_id: account?.id ?? null,
        cwd,
      })
      onOpened(run)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <DialogContent className="sm:max-w-lg">
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4">
        <DialogHeader>
          <DialogTitle>{t(`${n}.title`)}</DialogTitle>
          <DialogDescription>{t(`${n}.description`)}</DialogDescription>
        </DialogHeader>
        {clis.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t(`${n}.noCli`)}</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="terminal-cli">{t(`${n}.cli`)}</Label>
                <Select
                  value={chosenCli ?? undefined}
                  onValueChange={(id) => {
                    setCli(id as CliId)
                    setAccountId(null)
                  }}
                >
                  <SelectTrigger id="terminal-cli" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {clis.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="terminal-account">{t(`${n}.account`)}</Label>
                <Select value={account?.id} onValueChange={setAccountId}>
                  <SelectTrigger id="terminal-account" className="w-full">
                    <SelectValue placeholder={t(`${n}.defaultAccount`)} />
                  </SelectTrigger>
                  <SelectContent>
                    {ofCli.map((a) => (
                      <SelectItem key={a.id} value={a.id}>
                        {a.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1.5 text-sm font-medium">{t(`${n}.folder`)}</legend>
              <RadioGroup
                value={place}
                onValueChange={(value) => setPlace(value as Place)}
                className="gap-2"
              >
                {(['home', 'project', 'other'] as const).map((value) => (
                  <div key={value} className="flex items-center gap-2">
                    <RadioGroupItem
                      id={`terminal-place-${value}`}
                      value={value}
                      disabled={value === 'project' && projects.length === 0}
                    />
                    <Label htmlFor={`terminal-place-${value}`} className="font-normal">
                      {t(`${n}.places.${value}`)}
                    </Label>
                  </div>
                ))}
              </RadioGroup>
              {place === 'project' && (
                <Select value={project?.id} onValueChange={setProjectId}>
                  <SelectTrigger aria-label={t(`${n}.project`)} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {projects.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              {place === 'other' && (
                <FolderPicker id="terminal-folder" value={folder} onChange={setFolder} />
              )}
            </fieldset>
          </>
        )}
        <DialogFooter>
          <Button
            type="submit"
            disabled={!chosenCli || !cwd || openTerminal.isPending}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t(`${n}.submit`)}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}
