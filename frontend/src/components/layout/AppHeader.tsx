import { Plus, Search, SquareTerminal } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from '@/components/ui/breadcrumb'
import { Button } from '@/components/ui/button'
import type { NavItem } from './nav'

export function AppHeader({ section }: { section: NavItem }) {
  const { t } = useTranslation()
  const comingSoon = t('header.comingSoon')

  return (
    <header className="flex h-[52px] shrink-0 items-center gap-3 border-b bg-background px-[18px]">
      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="flex-nowrap gap-1.5 text-[13px]">
          <BreadcrumbItem>
            <BreadcrumbPage className="font-medium whitespace-nowrap">
              {t(`nav.${section.id}`)}
            </BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      <button
        type="button"
        disabled
        title={comingSoon}
        className="flex h-8 w-[300px] items-center gap-2 rounded-lg border bg-subtle pr-2 pl-2.5 text-[12.5px] text-muted-foreground disabled:cursor-not-allowed"
      >
        <Search className="size-3.5" />
        <span className="flex-1 text-left">{t('header.search')}</span>
        <kbd className="rounded border bg-card px-1.5 py-px font-mono text-[11px]">
          {t('header.searchShortcut')}
        </kbd>
      </button>
      <Button
        variant="outline"
        disabled
        title={comingSoon}
        className="h-8 gap-[7px] bg-transparent"
      >
        <SquareTerminal className="size-[15px]" />
        {t('header.terminal')}
      </Button>
      {section.primary && (
        <Button
          disabled
          title={comingSoon}
          className="h-8 gap-1.5 bg-primary-action font-medium text-white hover:bg-primary-action-hover"
        >
          <Plus className="size-[15px]" />
          {t(`header.primary.${section.primary}`)}
        </Button>
      )}
    </header>
  )
}
