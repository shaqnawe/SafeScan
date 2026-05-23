/**
 * Shared theme for SafeScan — Premium aesthetic (dark + light counterparts).
 *
 * Use `getTheme(isDark)` in any component for consistent colors, surfaces,
 * and gradients. Glassmorphism cards + amber-gold accent throughout.
 */

export interface Theme {
  // Page surface
  bg: string
  bgGradient: string

  // Glass cards
  glass: string
  glassBorder: string
  glassShadow: string
  divider: string

  // Text
  primary: string
  secondary: string
  tertiary: string

  // Brand accents
  accent: string
  accentDark: string
  accentSoft: string // 15%-alpha for backgrounds/badges
  gradeGradient: string

  // Misc surfaces
  ingredientBg: string
  ingredientBorder: string
  btnText: string
  ctaShadow: string
  ctaWrapBg: string

  // Status colors (universal across modes)
  green: string
  greenSoft: string
  red: string
  redSoft: string
}

export function getTheme(isDark: boolean): Theme {
  if (isDark) {
    return {
      bg: '#0a0a0f',
      bgGradient:
        'radial-gradient(at 0% 0%, rgba(245,158,11,0.18) 0px, transparent 50%),' +
        'radial-gradient(at 100% 100%, rgba(34,197,94,0.06) 0px, transparent 50%)',
      glass: 'rgba(24,24,32,0.6)',
      glassBorder: 'rgba(255,255,255,0.06)',
      glassShadow: '0 4px 24px rgba(0,0,0,0.4)',
      divider: 'rgba(255,255,255,0.04)',
      primary: '#fafafa',
      secondary: '#d4d4d8',
      tertiary: '#71717a',
      accent: '#fbbf24',
      accentDark: '#f59e0b',
      accentSoft: 'rgba(251,191,36,0.15)',
      gradeGradient: 'linear-gradient(135deg, #fbbf24, #f59e0b)',
      ingredientBg: 'rgba(255,255,255,0.03)',
      ingredientBorder: 'rgba(255,255,255,0.04)',
      btnText: '#0a0a0f',
      ctaShadow: '0 10px 30px rgba(251,191,36,0.3)',
      ctaWrapBg: 'linear-gradient(to top, #0a0a0f, transparent)',
      green: '#22c55e',
      greenSoft: 'rgba(34,197,94,0.15)',
      red: '#ef4444',
      redSoft: 'rgba(239,68,68,0.15)',
    }
  }
  return {
    bg: '#fafaf7',
    bgGradient:
      'radial-gradient(at 0% 0%, rgba(245,158,11,0.10) 0px, transparent 50%),' +
      'radial-gradient(at 100% 100%, rgba(34,197,94,0.08) 0px, transparent 50%)',
    glass: 'rgba(255,255,255,0.7)',
    glassBorder: 'rgba(0,0,0,0.06)',
    glassShadow: '0 4px 24px rgba(0,0,0,0.03)',
    divider: 'rgba(0,0,0,0.04)',
    primary: '#1a1a1f',
    secondary: '#3f3f46',
    tertiary: '#71717a',
    accent: '#d97706',
    accentDark: '#b45309',
    accentSoft: 'rgba(217,119,6,0.12)',
    gradeGradient: 'linear-gradient(135deg, #f59e0b, #d97706)',
    ingredientBg: 'rgba(255,255,255,0.6)',
    ingredientBorder: 'rgba(0,0,0,0.04)',
    btnText: '#fff',
    ctaShadow: '0 10px 30px rgba(245,158,11,0.3)',
    ctaWrapBg: 'linear-gradient(to top, #fafaf7, transparent)',
    green: '#16a34a',
    greenSoft: 'rgba(22,163,74,0.15)',
    red: '#dc2626',
    redSoft: 'rgba(220,38,38,0.12)',
  }
}

/** Grade-specific gradient for the giant grade letter. */
export function gradeGradient(grade: string, isDark: boolean): string {
  const map: Record<string, [string, string]> = isDark
    ? {
        A: ['#34d399', '#10b981'],
        B: ['#a3e635', '#84cc16'],
        C: ['#fbbf24', '#f59e0b'],
        D: ['#fb7185', '#ef4444'],
      }
    : {
        A: ['#10b981', '#047857'],
        B: ['#65a30d', '#4d7c0f'],
        C: ['#f59e0b', '#d97706'],
        D: ['#ef4444', '#b91c1c'],
      }
  const [from, to] = map[grade] || map.D
  return `linear-gradient(135deg, ${from}, ${to})`
}

/** Status indicator color + glow for safety levels. */
export const SAFETY_INDICATOR: Record<string, { color: string; glow: string }> = {
  safe:    { color: '#22c55e', glow: 'rgba(34,197,94,0.5)' },
  caution: { color: '#fbbf24', glow: 'rgba(251,191,36,0.5)' },
  avoid:   { color: '#ef4444', glow: 'rgba(239,68,68,0.5)' },
}

/** Glass card style — apply to any container that should look frosted. */
export function glassStyle(theme: Theme): React.CSSProperties {
  return {
    background: theme.glass,
    backdropFilter: 'blur(20px) saturate(180%)',
    WebkitBackdropFilter: 'blur(20px) saturate(180%)',
    border: `1px solid ${theme.glassBorder}`,
    borderRadius: 24,
    boxShadow: theme.glassShadow,
  }
}

export const FONT_STACK =
  '"Manrope", -apple-system, BlinkMacSystemFont, system-ui, sans-serif'
