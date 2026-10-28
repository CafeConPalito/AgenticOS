import { ArrowRight, Palette } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { isBuiltin } from '@/theme/builtin'
import { useTheme } from '@/theme/ThemeProvider'
import { ThemeSwatch } from './appearance/ThemeSwatch'

/** «Apariencia» in Ajustes (phase 20): the theme on screen and the way to the full page. */
export function AppearanceSection() {
  const { t } = useTranslation()
  const { appearance, resolved } = useTheme()
  const custom = appearance.custom.find((theme) => theme.id === resolved.id)
  const name =
    custom?.name ?? (isBuiltin(resolved.id) ? t(`appearance.builtin.${resolved.id}`) : resolved.id)
  return (
    <section
      aria-labelledby="appearance-title"
      className="flex flex-col gap-3 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <h2 id="appearance-title" className="flex items-center gap-2 text-[15px] font-medium">
        <Palette className="size-4" />
        {t('appearance.title')}
      </h2>
      <div className="flex flex-wrap items-center gap-4">
        <div className="w-[180px]">
          <ThemeSwatch theme={resolved} />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-[13px] font-medium">{name}</span>
          <span className="text-xs text-muted-foreground">
            {appearance.mode === 'system'
              ? t('appearance.section.system')
              : t('appearance.section.fixed')}
          </span>
        </div>
        <Button variant="outline" asChild>
          <Link to="/ajustes/apariencia">
            {t('appearance.section.open')}
            <ArrowRight />
          </Link>
        </Button>
      </div>
    </section>
  )
}
