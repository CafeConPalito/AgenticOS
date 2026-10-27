import { Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import { useCreateTeam, useDeleteTeam, useTeams, useUpdateTeam } from '@/api/teams'
import type { Team } from '@/api/types'
import { AgentAvatar } from '@/components/agentic/primitives'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Field } from '@/components/page'
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
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'

/**
 * «Nuevo equipo» / «Editar equipo»: a name, what it is for and who belongs to it. An agent is in
 * one team: choosing it here takes it out of the one it was in.
 */
export function TeamDialog({
  team,
  onClose,
}: {
  /** `'new'`: creating; a team: editing it; null: closed. */
  team: Team | 'new' | null
  onClose: () => void
}) {
  return (
    <Dialog open={team !== null} onOpenChange={(open) => !open && onClose()}>
      {team !== null && <TeamForm team={team === 'new' ? null : team} onClose={onClose} />}
    </Dialog>
  )
}

function TeamForm({ team, onClose }: { team: Team | null; onClose: () => void }) {
  const { t } = useTranslation()
  const agents = useAgents().data ?? []
  const teams = useTeams().data ?? []
  const create = useCreateTeam()
  const update = useUpdateTeam(team?.id ?? '')
  const remove = useDeleteTeam()
  const [name, setName] = useState(team?.name ?? '')
  const [description, setDescription] = useState(team?.description ?? '')
  const [members, setMembers] = useState<string[]>(team?.agent_ids ?? [])
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const busy = create.isPending || update.isPending || remove.isPending

  const teamOf = (agentId: string) =>
    teams.find((x) => x.agent_ids.includes(agentId) && x.id !== team?.id)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setError(null)
    const body = { name: name.trim(), description: description.trim(), agent_ids: members }
    try {
      if (team) await update.mutateAsync(body)
      else await create.mutateAsync(body)
      toast.success(t(team ? 'teams.saved' : 'teams.created', { name: body.name }))
      onClose()
    } catch (failure) {
      setError(errorMessage(failure))
    }
  }

  async function onDelete() {
    if (!team) return
    try {
      await remove.mutateAsync(team.id)
      toast.success(t('teams.deleted', { name: team.name }))
      onClose()
    } catch (failure) {
      toast.error(errorMessage(failure))
    }
  }

  return (
    <DialogContent className="max-h-[calc(100vh-48px)] overflow-y-auto sm:max-w-[520px]">
      <form onSubmit={(e) => void submit(e)} className="grid gap-4">
        <DialogHeader>
          <DialogTitle>{team ? t('teams.editTitle') : t('teams.newTitle')}</DialogTitle>
          <DialogDescription>{t('teams.description')}</DialogDescription>
        </DialogHeader>
        <Field label={t('teams.name')} htmlFor="team-name">
          <Input
            id="team-name"
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('teams.namePlaceholder')}
          />
        </Field>
        <Field label={t('teams.purpose')} htmlFor="team-description">
          <Textarea
            id="team-description"
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <fieldset className="grid gap-1.5">
          <legend className="mb-1 text-xs text-muted-foreground">{t('teams.members')}</legend>
          {agents.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t('teams.noAgents')}</p>
          ) : (
            <ul className="max-h-[220px] overflow-y-auto rounded-lg border">
              {agents.map((agent) => {
                const elsewhere = teamOf(agent.id)
                const checked = members.includes(agent.id)
                return (
                  <li key={agent.id} className="border-b last:border-b-0">
                    <label className="flex cursor-pointer items-center gap-2.5 px-3 py-2 hover:bg-subtle">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          setMembers((list) =>
                            checked ? list.filter((id) => id !== agent.id) : [...list, agent.id],
                          )
                        }
                      />
                      <AgentAvatar name={agent.name} color={agent.color} size={20} />
                      <span className="text-[13px]">{agent.name}</span>
                      {elsewhere && checked && (
                        <span className="ml-auto text-xs text-status-waiting">
                          {t('teams.moves', { team: elsewhere.name })}
                        </span>
                      )}
                      {elsewhere && !checked && (
                        <span className="ml-auto text-xs text-muted-foreground">
                          {t('teams.inTeam', { team: elsewhere.name })}
                        </span>
                      )}
                    </label>
                  </li>
                )
              })}
            </ul>
          )}
        </fieldset>
        {error && (
          <p role="alert" className="text-sm text-status-failed">
            {error}
          </p>
        )}
        <DialogFooter className="gap-2 sm:items-center">
          {team && (
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={() => setConfirming(true)}
              className="text-status-failed sm:mr-auto"
            >
              <Trash2 />
              {t('teams.delete')}
            </Button>
          )}
          {team && (
            <Button type="button" variant="outline" asChild>
              <Link to={`/agentes/arquitecto?equipo=${team.id}`} onClick={onClose}>
                <Sparkles className="text-status-review" />
                {t('architect.improve')}
              </Link>
            </Button>
          )}
          <Button type="button" variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            disabled={!name.trim() || busy}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {team ? t('common.save') : t('teams.create')}
          </Button>
        </DialogFooter>
      </form>
      {team && (
        <ConfirmDialog
          open={confirming}
          onOpenChange={setConfirming}
          title={t('teams.deleteTitle', { name: team.name })}
          description={t('teams.deleteDescription')}
          confirmLabel={t('teams.delete')}
          destructive
          onConfirm={() => void onDelete()}
        />
      )}
    </DialogContent>
  )
}
