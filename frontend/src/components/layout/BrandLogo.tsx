import logo from '@/assets/brand/ccp-logo.png'
import negative from '@/assets/brand/ccp-logo-negative.png'
import { useTheme } from '@/theme/ThemeProvider'

/** The Café con Palito logo: the navy one on light themes, the white one on dark themes. */
export function BrandLogo({ size = 96 }: { size?: number }) {
  const { theme } = useTheme()
  return (
    <img
      src={theme === 'dark' ? negative : logo}
      alt="Café con Palito"
      style={{ height: size }}
      className="w-auto select-none"
      draggable={false}
    />
  )
}
