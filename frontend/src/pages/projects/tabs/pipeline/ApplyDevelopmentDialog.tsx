import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAccounts } from '@/api/accounts'
import { useAgents } from '@/api/agents'
import { useClis } from '@/api/clis'
import { usePipelineFromTemplate, useTemplatePlan } from '@/api/pipelines'
import { useTeams } from '@/api/teams'
import type { CliId } from '@/api/types'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { errorMessage } from '@/lib/form-errors'

/** The stage keeps what the template gives it: its agent, or a new one made from it. */
const TEMPLATE = '__template__'
const DEFAULT_ACCOUNT = '__default__'
const NEW_TEAM = '__new__'

/**
 * Phase 24: applies «Desarrollo» to a project. Each stage shows the agent it gets (one made from
 * its template, or «se creará»), which the person can swap for any active agent; the missing
 * ones are created in one step with the CLI, account and model chosen here, in one team.
 */
export function ApplyDevelopmentDialog({
  open,
  onOpenChange,
  projectId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectId: string
}) {
  const { t } = useTranslation()
  const d = 'pipeline.development'
  const plan = useTemplatePlan('development', open).data ?? []
  const agents = (useAgents().data ?? []).filter((a) => a.status === 'active')
  const clis = (useClis().data ?? []).filter((c) => c.installed)
  const accounts = useAccounts().data ?? []
  const teams = useTeams().data ?? []
  const apply = usePipelineFromTemplate(projectId)

  const [assign, setAssign] = useState<Record<number, string>>({})
  const [cli, setCli] = useState<CliId | ''>('')
  const [account, setAccount] = useState(DEFAULT_ACCOUNT)
  const [model, setModel] = useState('')
  const [team, setTeam] = useState(NEW_TEAM)
  const [teamName, setTeamName] = useState('Desarrollo')

  const chosenCli = (cli || clis[0]?.id || 'claude') as CliId
  const cliAccounts = accounts.filter((a) => a.cli === chosenCli)
  const toCreate = plan.filter((s) => (assign[s.index] ?? TEMPLATE) === TEMPLATE && !s.agent_id)

  async function onApply() {
    const picked = Object.fromEntries(
      Object.entries(assign).filter(([, value]) => value !== TEMPLATE),
    )
    try {
      await apply.mutateAsync({
        template: 'development',
        assign: picked,
        create:
          toCreate.length > 0
            ? {
                cli: chosenCli,
                account_id: account === DEFAULT_ACCOUNT ? null : account,
                model: model.trim() || null,
                ...(team === NEW_TEAM
                  ? { team_name: teamName.trim() || 'Desarrollo' }
                  : { team_id: team }),
              }
            : null,
      })
      toast.success(t(`${d}.applied`, { count: toCreate.length }))
      onOpenChange(false)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t(`${d}.title`)}</DialogTitle>
          <DialogDescription>{t(`${d}.description`)}</DialogDescription>
        </DialogHeader>
        <ul aria-label={t(`${d}.stages`)} className="grid gap-1.5">
          {plan.map((stage) => {
            const value = assign[stage.index] ?? TEMPLATE
            return (
              <li
                key={stage.index}
                className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] items-center gap-3 text-[13px]"
              >
                <span className="truncate font-medium">{stage.name}</span>
                <Select
                  value={value}
                  onValueChange={(v) => setAssign((a) => ({ ...a, [stage.index]: v }))}
                >
                  <SelectTrigger
                    aria-label={t(`${d}.agentFor`, { stage: stage.name })}
                    className="h-8"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={TEMPLATE}>
                      {stage.agent_name
                        ? t(`${d}.exists`, { name: stage.agent_name })
                        : t(`${d}.willCreate`, { name: stage.template_name })}
                    </SelectItem>
                    {agents
                      .filter((a) => a.id !== stage.agent_id)
                      .map((a) => (
                        <SelectItem key={a.id} value={a.id}>
                          {a.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </li>
            )
          })}
        </ul>

        {toCreate.length > 0 && (
          <fieldset className="grid gap-3 rounded-lg border p-3">
            <legend className="px-1 text-[12.5px] font-medium">
              {t(`${d}.newAgents`, { count: toCreate.length })}
            </legend>
            <div className="grid grid-cols-2 gap-3">
              <label className="grid gap-1 text-[13px]">
                {t(`${d}.cli`)}
                <Select
                  value={chosenCli}
                  onValueChange={(v) => {
                    setCli(v as CliId)
                    setAccount(DEFAULT_ACCOUNT)
                  }}
                >
                  <SelectTrigger aria-label={t(`${d}.cli`)} className="h-8">
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
              </label>
              <label className="grid gap-1 text-[13px]">
                {t(`${d}.account`)}
                <Select value={account} onValueChange={setAccount}>
                  <SelectTrigger aria-label={t(`${d}.account`)} className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DEFAULT_ACCOUNT}>{t(`${d}.defaultAccount`)}</SelectItem>
                    {cliAccounts.map((a) => (
                      <SelectItem key={a.id} value={a.id}>
                        {a.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <label className="grid gap-1 text-[13px]">
                {t(`${d}.model`)}
                <Input
                  value={model}
                  maxLength={80}
                  placeholder={t(`${d}.modelPlaceholder`)}
                  onChange={(e) => setModel(e.target.value)}
                  className="h-8"
                />
              </label>
              <label className="grid gap-1 text-[13px]">
                {t(`${d}.team`)}
                <Select value={team} onValueChange={setTeam}>
                  <SelectTrigger aria-label={t(`${d}.team`)} className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NEW_TEAM}>{t(`${d}.newTeam`)}</SelectItem>
                    {teams.map((tm) => (
                      <SelectItem key={tm.id} value={tm.id}>
                        {tm.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              {team === NEW_TEAM && (
                <label className="col-span-2 grid gap-1 text-[13px]">
                  {t(`${d}.teamName`)}
                  <Input
                    value={teamName}
                    maxLength={80}
                    onChange={(e) => setTeamName(e.target.value)}
                    className="h-8"
                  />
                </label>
              )}
            </div>
            <p className="text-[12.5px] text-muted-foreground">{t(`${d}.costNote`)}</p>
          </fieldset>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={apply.isPending || plan.length === 0}
            onClick={() => void onApply()}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {toCreate.length > 0
              ? t(`${d}.applyAndCreate`, { count: toCreate.length })
              : t(`${d}.apply`)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
