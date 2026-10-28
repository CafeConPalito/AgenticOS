import { ArrowRight, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'

/** «Acerca de» in Ajustes (phase 08; since phase 20 the full page is /acerca-de). */
export function AboutSection() {
  const { t } = useTranslation()
  return (
    <section
      aria-labelledby="about-title"
      className="flex flex-col gap-3 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <h2 id="about-title" className="flex items-center gap-2 text-[15px] font-medium">
        <Info className="size-4" />
        {t('settings.about.title')}
      </h2>
      <div className="flex flex-wrap items-center gap-4">
        <p className="flex-1 text-[13px] text-muted-foreground">
          {t('settings.about.summary', { version: __APP_VERSION__ })}
        </p>
        <Button variant="outline" asChild>
          <Link to="/acerca-de">
            {t('settings.about.open')}
            <ArrowRight />
          </Link>
        </Button>
      </div>
    </section>
  )
}
