import { Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar'
import type { BackendState } from '@/hooks/useHealth'
import { useTheme } from '@/theme/ThemeProvider'
import { BackendStatus } from './BackendStatus'
import { Logo } from './Logo'
import { NAV, type Section } from './nav'

const ITEM_CLASS =
  'text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-accent-foreground data-[active=true]:bg-sidebar-accent data-[active=true]:text-sidebar-accent-foreground h-[34px] gap-2.5 rounded-[7px] data-[active=true]:font-medium'

export function AppSidebar({
  active,
  inboxCount,
  backendState,
  backendVersion,
}: {
  active: Section
  inboxCount: number
  backendState: BackendState
  backendVersion?: string
}) {
  const { t } = useTranslation()
  const { state } = useSidebar()
  const { theme, toggleTheme } = useTheme()
  const expanded = state === 'expanded'

  return (
    <Sidebar collapsible="icon" className="border-sidebar-border">
      <SidebarHeader className="h-[52px] flex-row items-center gap-2.5 border-b border-sidebar-border px-3.5">
        <Logo />
        {expanded && (
          <span className="flex-1 text-[15px] font-bold tracking-[-0.01em] whitespace-nowrap">
            {t('app.name')}
          </span>
        )}
        <SidebarTrigger
          className="text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          aria-label={t('nav.collapse')}
        />
      </SidebarHeader>
      <SidebarContent className="px-2.5 py-2.5">
        <nav aria-label={t('nav.main')}>
          <SidebarMenu className="gap-0.5">
            {NAV.map(({ id, path, icon: Icon }) => (
              <SidebarMenuItem key={id}>
                <SidebarMenuButton
                  asChild
                  isActive={active === id}
                  tooltip={t(`nav.${id}`)}
                  className={ITEM_CLASS}
                >
                  <NavLink to={path} end={path === '/'}>
                    <Icon className="size-4" />
                    <span>{t(`nav.${id}`)}</span>
                  </NavLink>
                </SidebarMenuButton>
                {id === 'inbox' && inboxCount > 0 && (
                  <SidebarMenuBadge className="h-[18px] min-w-5 rounded-full bg-status-waiting px-1.5 text-[11px] font-bold text-[#0A1A33]">
                    {inboxCount}
                  </SidebarMenuBadge>
                )}
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </nav>
      </SidebarContent>
      <SidebarFooter className="gap-1.5 border-t border-sidebar-border p-2.5">
        <BackendStatus state={backendState} version={backendVersion} compact={!expanded} />
        <SidebarMenuButton
          onClick={toggleTheme}
          tooltip={t('theme.toggle')}
          className="h-8 gap-[9px] text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        >
          {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          <span>{theme === 'dark' ? t('theme.toLight') : t('theme.toDark')}</span>
        </SidebarMenuButton>
      </SidebarFooter>
    </Sidebar>
  )
}
