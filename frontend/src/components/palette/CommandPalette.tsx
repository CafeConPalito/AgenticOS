import {
  ArrowRight,
  Bot,
  CircleDot,
  Folder,
  FolderPlus,
  Keyboard,
  Pause,
  Play,
  Plus,
  Sparkles,
  SunMoon,
  Terminal,
  UserPlus,
  UsersRound,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import { useScheduler, useSetSchedulerPaused, useTaskSearch } from '@/api/tasks'
import { useDock } from '@/components/terminal/dock-store'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSearchBar,
} from '@/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { SHORTCUTS } from '@/lib/shortcuts'
import { errorMessage } from '@/lib/form-errors'
import { useDialogs } from '@/stores/dialogs'
import { useTheme } from '@/theme/ThemeProvider'
import { Kbd } from './Kbd'

/** At most this many results while searching. */
export const MAX_RESULTS = 14
/** Slots kept for task matches when searching. */
const MAX_TASK_RESULTS = 6
/** Agents suggested before typing anything. */
const SUGGESTED_AGENTS = 6
const DEBOUNCE_MS = 150

type Group = 'actions' | 'goto' | 'agents' | 'projects' | 'tasks'

export interface PaletteItem {
  id: string
  group: Group
  label: string
  icon: LucideIcon
  keys?: string[]
  run: () => void
}

/** Lower case without accents, so «diseno» finds «Diseño». */
export const fold = (text: string) =>
  text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim()

const keysOf = (id: string) => SHORTCUTS.find((s) => s.id === id)?.keys

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <PaletteContent onClose={() => onOpenChange(false)} />}
    </Dialog>
  )
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

function PaletteContent({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()
  const dialogs = useDialogs.getState()
  const toggleDock = useDock((s) => s.toggle)
  const [query, setQuery] = useState('')
  const debounced = useDebounced(query, DEBOUNCE_MS)
  const agents = useAgents().data
  const projects = useProjects().data
  const tasks = useTaskSearch(debounced).data
  const scheduler = useScheduler().data
  const setPaused = useSetSchedulerPaused()
  const needle = fold(query)

  const items = useMemo<PaletteItem[]>(() => {
    const go = (path: string) => () => void navigate(path)
    const paused = scheduler?.paused === true
    const actions: PaletteItem[] = [
      {
        id: 'new-task',
        group: 'actions',
        label: t('palette.actions.newTask'),
        icon: Plus,
        keys: keysOf('newTask'),
        run: () => dialogs.openNewTask(),
      },
      {
        id: 'new-agent',
        group: 'actions',
        label: t('palette.actions.newAgent'),
        icon: Bot,
        run: () => dialogs.openNewAgent(),
      },
      {
        id: 'architect',
        group: 'actions',
        label: t('palette.actions.architect'),
        icon: Sparkles,
        run: go('/agentes/arquitecto?nueva'),
      },
      {
        id: 'new-team',
        group: 'actions',
        label: t('palette.actions.newTeam'),
        icon: UsersRound,
        run: () => dialogs.openTeam(),
      },
      {
        id: 'add-account',
        group: 'actions',
        label: t('palette.actions.addAccount'),
        icon: UserPlus,
        run: go('/clis?nueva=1'),
      },
      {
        id: 'new-project',
        group: 'actions',
        label: t('palette.actions.newProject'),
        icon: FolderPlus,
        run: () => dialogs.openNewProject(),
      },
      {
        id: 'terminal',
        group: 'actions',
        label: t('palette.actions.openTerminal'),
        icon: Terminal,
        keys: keysOf('dock'),
        run: toggleDock,
      },
      {
        id: 'theme',
        group: 'actions',
        label: t('palette.actions.toggleTheme'),
        icon: SunMoon,
        run: toggleTheme,
      },
      ...(scheduler
        ? [
            {
              id: 'scheduler',
              group: 'actions' as const,
              label: t(
                paused ? 'palette.actions.resumeScheduler' : 'palette.actions.pauseScheduler',
              ),
              icon: paused ? Play : Pause,
              run: () =>
                setPaused.mutate(!paused, {
                  onSuccess: () =>
                    toast.success(
                      t(paused ? 'palette.schedulerResumed' : 'palette.schedulerPaused'),
                    ),
                  onError: (error) => toast.error(errorMessage(error)),
                }),
            },
          ]
        : []),
      {
        id: 'shortcuts',
        group: 'actions',
        label: t('palette.actions.shortcuts'),
        icon: Keyboard,
        keys: keysOf('shortcuts'),
        run: () => dialogs.openShortcuts(),
      },
    ]
    const goto: PaletteItem[] = (
      [
        ['home', '/'],
        ['projects', '/proyectos'],
        ['agents', '/agentes'],
        ['board', '/tablero'],
        ['runs', '/ejecuciones'],
        ['usage', '/consumo'],
        ['clis', '/clis'],
        ['knowledge', '/conocimiento'],
        ['connections', '/conexiones'],
        ['inbox', '/inbox'],
        ['settings', '/ajustes'],
        ['appearance', '/ajustes/apariencia'],
      ] as const
    ).map(([id, path]) => ({
      id: `go-${id}`,
      group: 'goto' as const,
      label: t(`palette.goto.${id}`),
      icon: ArrowRight,
      run: go(path),
    }))
    return [
      ...actions,
      ...goto,
      ...(agents ?? []).map((a) => ({
        id: `agent-${a.id}`,
        group: 'agents' as const,
        label: a.role ? `${a.name} · ${a.role}` : a.name,
        icon: Bot,
        run: go(`/agentes/${a.id}`),
      })),
      ...(projects ?? []).map((p) => ({
        id: `project-${p.id}`,
        group: 'projects' as const,
        label: p.name,
        icon: Folder,
        run: go(`/proyectos/${p.id}`),
      })),
    ]
    // `dialogs` is the store's own (stable) action set.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, navigate, agents, projects, scheduler, toggleDock, toggleTheme, theme])

  const taskItems = useMemo<PaletteItem[]>(
    () =>
      needle
        ? (tasks ?? [])
            .map((task) => ({
              id: `task-${task.id}`,
              group: 'tasks' as const,
              label: `${task.code} · ${task.title}`,
              icon: CircleDot,
              run: () => void navigate(`/tablero/tareas/${task.id}`),
            }))
            // The results lag behind the input (debounce): drop the ones it no longer matches.
            .filter((i) => fold(i.label).includes(needle))
            .slice(0, MAX_TASK_RESULTS)
        : [],
    [needle, tasks, navigate],
  )

  // Without a search: actions, sections and agents. Searching: everything that matches.
  const shown = needle
    ? [
        // Tasks keep their slots: the actions and agents that match must not push them out.
        ...items
          .filter((i) => fold(i.label).includes(needle))
          .slice(0, MAX_RESULTS - taskItems.length),
        ...taskItems,
      ]
    : [
        ...items.filter((i) => i.group === 'actions' || i.group === 'goto'),
        ...items.filter((i) => i.group === 'agents').slice(0, SUGGESTED_AGENTS),
      ]
  const groups = (['actions', 'goto', 'agents', 'projects', 'tasks'] as const).filter((g) =>
    shown.some((i) => i.group === g),
  )

  return (
    <DialogContent
      showCloseButton={false}
      className="top-[12vh] max-h-[470px] w-[600px] max-w-[calc(100vw-40px)] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-[600px]"
    >
      <DialogTitle className="sr-only">{t('palette.title')}</DialogTitle>
      <DialogDescription className="sr-only">{t('palette.placeholder')}</DialogDescription>
      <Command shouldFilter={false} vimBindings={false} className="bg-transparent" loop>
        <CommandSearchBar>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder={t('palette.placeholder')}
            aria-label={t('palette.title')}
            className="h-full text-foreground"
          />
          <Kbd keys={['Esc']} />
        </CommandSearchBar>
        <CommandList className="max-h-none flex-1 p-1.5">
          <CommandEmpty className="px-2.5 py-[18px] text-left text-muted-foreground">
            {t('palette.empty')}
          </CommandEmpty>
          {groups.map((group) => (
            <CommandGroup key={group} heading={t(`palette.groups.${group}`)}>
              {shown
                .filter((i) => i.group === group)
                .map((item) => (
                  <CommandItem
                    key={item.id}
                    value={item.id}
                    onSelect={() => {
                      onClose()
                      item.run()
                    }}
                    className="h-9 gap-2.5 rounded-[10px] px-2.5"
                  >
                    <item.icon className="size-[15px] text-muted-foreground" />
                    <span className="flex-1 truncate">{item.label}</span>
                    {item.keys && <Kbd keys={item.keys} />}
                  </CommandItem>
                ))}
            </CommandGroup>
          ))}
        </CommandList>
      </Command>
    </DialogContent>
  )
}
