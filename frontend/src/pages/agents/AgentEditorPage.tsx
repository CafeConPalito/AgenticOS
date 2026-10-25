import { zodResolver } from '@hookform/resolvers/zod'
import { BookOpen, Copy, MoreHorizontal, Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { FormProvider, useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import {
  useAgent,
  useClearFallback,
  useDeleteAgent,
  useDuplicateAgent,
  useUpdateAgent,
} from '@/api/agents'
import type { Agent } from '@/api/types'
import { AgentAvatar, StatusBadge } from '@/components/agentic/primitives'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { KnowledgeLibrary } from '@/components/knowledge/KnowledgeLibrary'
import { AgentConnections } from '@/components/connections/AgentConnections'
import { SkillLibrary } from '@/components/skills/SkillLibrary'
import { SkillModes } from '@/components/skills/SkillModes'
import { PageContainer, RouteTabs } from '@/components/page'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { applyApiError, errorMessage } from '@/lib/form-errors'
import { LaunchRunButton } from '@/pages/runs/LaunchRunDialog'
import { useDialogs } from '@/stores/dialogs'
import { AGENT_FIELDS, agentSchema, changedFields, toFormValues } from './agent-form'
import type { AgentFormValues } from './agent-form'
import { ExecutionTab } from './tabs/ExecutionTab'
import { ChangesTab } from './tabs/ChangesTab'
import { HistoryTab } from './tabs/HistoryTab'
import { GeneralTab } from './tabs/GeneralTab'
import { SummaryTab } from './tabs/SummaryTab'
import { InstructionsTab } from './tabs/InstructionsTab'

const TABS = [
  'resumen',
  'general',
  'instructions',
  'execution',
  'knowledge',
  'skills',
  'connections',
  'history',
  'changes',
] as const
type Tab = (typeof TABS)[number]

export default function AgentEditorPage() {
  const { agentId = '', tab } = useParams()
  const { t } = useTranslation()
  const { data: agent, isPending, isError } = useAgent(agentId)

  if (!TABS.includes(tab as Tab)) return <Navigate to={`/agentes/${agentId}/resumen`} replace />
  if (isPending)
    return (
      <PageContainer>
        <Skeleton aria-busy className="h-24 rounded-lg" />
      </PageContainer>
    )
  if (isError || !agent)
    return (
      <PageContainer>
        <EmptyState icon={BookOpen} title={t('agents.notFound')} />
      </PageContainer>
    )
  return <AgentEditor key={agent.id} agent={agent} tab={tab as Tab} />
}

function AgentEditor({ agent, tab }: { agent: Agent; tab: Tab }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const update = useUpdateAgent(agent.id)
  const clearFallback = useClearFallback()
  const duplicate = useDuplicateAgent()
  const remove = useDeleteAgent()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const openNewTask = useDialogs((s) => s.openNewTask)
  const leaving = useRef(false)

  const schema = useMemo(() => agentSchema(), [])
  const form = useForm<AgentFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toFormValues(agent),
    mode: 'onChange',
  })
  const { isDirty, dirtyFields } = form.formState
  const [name, role, color, cli, model, status] = useWatch({
    control: form.control,
    name: ['name', 'role', 'color', 'cli', 'model', 'status'],
  })

  // Keep the form in sync when the agent is refetched and the user has no pending edits.
  useEffect(() => {
    if (!form.formState.isDirty) form.reset(toFormValues(agent))
  }, [agent, form])

  const save = form.handleSubmit(async (values) => {
    try {
      const saved = await update.mutateAsync(changedFields(values, dirtyFields))
      form.reset(toFormValues(saved))
      toast.success(t('common.saved'))
    } catch (error) {
      applyApiError(error, form.setError, AGENT_FIELDS)
    }
  })

  async function onActivate() {
    try {
      const saved = await update.mutateAsync({ status: 'active' })
      // Keep what the person is editing; only the status is settled.
      form.reset(toFormValues(saved), { keepDirtyValues: true })
      toast.success(t('agents.activated', { name: saved.name }))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function onDuplicate() {
    try {
      const copy = await duplicate.mutateAsync({
        id: agent.id,
        name: t('agents.copyName', { name: agent.name }),
      })
      leaving.current = !form.formState.isDirty
      toast.success(t('agents.duplicated', { name: copy.name }))
      navigate(`/agentes/${copy.id}`)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function onDelete() {
    try {
      await remove.mutateAsync(agent.id)
      leaving.current = true // the agent is gone: nothing left to save
      toast.success(t('agents.delete.done', { name: agent.name }))
      navigate('/agentes')
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const tabs = TABS.map((id) => ({ id, label: t(`agents.tabs.${id}`) }))

  return (
    <FormProvider {...form}>
      <form onSubmit={save} noValidate className="flex min-h-full flex-col">
        <UnsavedChangesGuard when={isDirty} allowRef={leaving} scope={`/agentes/${agent.id}`} />
        <header className="flex items-center gap-4 px-6 pt-[22px] pb-4">
          <AgentAvatar name={name || '?'} color={color} size={52} />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[26px] leading-[1.2] font-bold tracking-[-0.028em]">
              {name}
              {role && <span className="font-normal text-muted-foreground"> · {role}</span>}
            </h1>
            <div className="mt-1 flex items-center gap-2 text-[12.5px] text-muted-foreground">
              <StatusBadge
                tone={status === 'draft' ? 'review' : 'queued'}
                label={t(`agents.status.${status}`)}
                size="xs"
              />
              <span>{t(`cli.${cli}`)}</span>
              <span aria-hidden>·</span>
              <span className="font-mono">{model || t('cli.defaultModel')}</span>
              {agent.using_fallback && (
                <>
                  <StatusBadge tone="waiting" label={t('agents.usingFallback')} size="xs" />
                  <button
                    type="button"
                    className="text-xs underline hover:text-foreground"
                    onClick={() => clearFallback.mutate(agent.id)}
                  >
                    {t('agents.backToMain')}
                  </button>
                </>
              )}
            </div>
          </div>
          <Button
            type="button"
            onClick={() => openNewTask({ agentId: agent.id })}
            disabled={status === 'draft'}
            className="rounded-full bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <Plus />
            {t('agents.assignTask')}
          </Button>
          {status === 'draft' && (
            <Button
              type="button"
              variant="outline"
              className="rounded-full"
              disabled={update.isPending}
              onClick={() => void onActivate()}
            >
              {t('agents.activate')}
            </Button>
          )}
          <LaunchRunButton agentId={agent.id} disabled={agent.status === 'draft'} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="outline" size="icon" aria-label={t('common.more')}>
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => void onDuplicate()}>
                <Copy />
                {t('common.duplicate')}
              </DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}>
                <Trash2 />
                {t('common.delete')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {tab === 'resumen' ? (
            <Button type="button" variant="outline" asChild>
              <Link to={`/agentes/${agent.id}/general`}>
                <Pencil />
                {t('agents.edit')}
              </Link>
            </Button>
          ) : (
            <Button
              type="submit"
              disabled={!isDirty || update.isPending}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              {update.isPending ? t('common.saving') : t('common.save')}
            </Button>
          )}
        </header>
        <RouteTabs base={`/agentes/${agent.id}`} tabs={tabs} label={t('agents.title')} />
        {tab === 'resumen' && <SummaryTab agent={agent} />}
        {tab === 'general' && <GeneralTab />}
        {tab === 'instructions' && <InstructionsTab />}
        {tab === 'execution' && <ExecutionTab />}
        {tab === 'history' && <HistoryTab agentId={agent.id} />}
        {tab === 'changes' && <ChangesTab agentId={agent.id} />}
      </form>
      {/* Outside the form: the library has forms of its own. */}
      {tab === 'knowledge' && <KnowledgeLibrary level={{ scope: 'agent', agentId: agent.id }} />}
      {tab === 'skills' && (
        <>
          <SkillLibrary level={{ scope: 'agent', agentId: agent.id }} />
          <div className="px-6 pb-8">
            <SkillModes agentId={agent.id} agentCli={agent.cli} />
          </div>
        </>
      )}
      {tab === 'connections' && <AgentConnections agentId={agent.id} />}
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t('agents.delete.title', { name: agent.name })}
        description={t('agents.delete.description')}
        confirmLabel={t('common.delete')}
        destructive
        onConfirm={() => void onDelete()}
      />
    </FormProvider>
  )
}
