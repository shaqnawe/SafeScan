import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

export type ThemeMode = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'safescan:theme-mode'

function readStored(): ThemeMode {
  if (typeof window === 'undefined') return 'system'
  const v = window.localStorage.getItem(STORAGE_KEY)
  return v === 'light' || v === 'dark' || v === 'system' ? v : 'system'
}

export interface ThemeControls {
  isDark:    boolean
  mode:      ThemeMode
  setMode:   (m: ThemeMode) => void
  cycleMode: () => void   // system → light → dark → system
}

export function useDarkMode(): ThemeControls {
  const [mode, setModeState] = useState<ThemeMode>(readStored)
  const [systemDark, setSystemDark] = useState(
    () => typeof window !== 'undefined'
      && window.matchMedia('(prefers-color-scheme: dark)').matches
  )

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const setMode = useCallback((m: ThemeMode) => {
    setModeState(m)
    try { window.localStorage.setItem(STORAGE_KEY, m) } catch { /* private mode */ }
  }, [])

  const cycleMode = useCallback(() => {
    setMode(mode === 'system' ? 'light' : mode === 'light' ? 'dark' : 'system')
  }, [mode, setMode])

  const isDark = mode === 'system' ? systemDark : mode === 'dark'

  return { isDark, mode, setMode, cycleMode }
}

// ---------------------------------------------------------------------------
// Context — mount <ThemeProvider> once at the root, then any descendant can
// call useTheme() to read isDark / mode and cycle it via <ThemeToggle/>.
// ---------------------------------------------------------------------------

const ThemeContext = createContext<ThemeControls | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const controls = useDarkMode()
  return (
    <ThemeContext.Provider value={controls}>{children}</ThemeContext.Provider>
  )
}

export function useTheme(): ThemeControls {
  const v = useContext(ThemeContext)
  if (!v) throw new Error('useTheme must be used inside <ThemeProvider>')
  return v
}
