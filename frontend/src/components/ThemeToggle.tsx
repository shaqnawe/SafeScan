import { Monitor, Sun, Moon, type LucideIcon } from 'lucide-react'
import { useTheme, type ThemeMode } from '../hooks/useDarkMode'
import { getTheme, glassStyle, FONT_STACK } from '../theme'

interface ThemeToggleProps {
  /** Use 'icon' on pages where space is tight (header bars). 'pill' shows the label too. */
  variant?: 'pill' | 'icon'
}

const ICONS: Record<ThemeMode, { Icon: LucideIcon; label: string }> = {
  system: { Icon: Monitor, label: 'Auto'  },
  light:  { Icon: Sun,     label: 'Light' },
  dark:   { Icon: Moon,    label: 'Dark'  },
}

export default function ThemeToggle({ variant = 'pill' }: ThemeToggleProps) {
  const { isDark, mode, cycleMode } = useTheme()
  const theme = getTheme(isDark)
  const { Icon, label } = ICONS[mode]

  if (variant === 'icon') {
    return (
      <button
        onClick={cycleMode}
        aria-label={`Theme: ${label}. Click to cycle.`}
        title={`Theme: ${label}`}
        className="press"
        style={{
          background: theme.ingredientBg,
          border: `1px solid ${theme.glassBorder}`,
          borderRadius: '50%',
          width: 36,
          height: 36,
          cursor: 'pointer',
          color: theme.secondary,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          fontFamily: FONT_STACK,
        }}
      >
        <Icon size={16} strokeWidth={2} aria-hidden />
      </button>
    )
  }

  return (
    <button
      onClick={cycleMode}
      aria-label={`Theme: ${label}. Click to cycle.`}
      title={`Theme: ${label}`}
      className="press"
      style={{
        ...glassStyle(theme),
        borderRadius: 999,
        padding: '8px 12px',
        color: theme.secondary,
        fontSize: 13,
        fontWeight: 600,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        boxShadow: 'none',
        minWidth: 40,
        justifyContent: 'center',
        fontFamily: FONT_STACK,
      }}
    >
      <Icon size={15} strokeWidth={2} aria-hidden />
      <span style={{ fontSize: 12 }}>{label}</span>
    </button>
  )
}
