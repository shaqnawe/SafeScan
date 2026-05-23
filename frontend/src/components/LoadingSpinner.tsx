import { getTheme, FONT_STACK } from '../theme'

interface LoadingSpinnerProps {
  message?: string
  isDark?: boolean
}

export default function LoadingSpinner({
  message = 'Analyzing product...',
  isDark = false,
}: LoadingSpinnerProps) {
  const theme = getTheme(isDark)

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        gap: 24,
        background: theme.bg,
        backgroundImage: theme.bgGradient,
        color: theme.primary,
        padding: 24,
        fontFamily: FONT_STACK,
      }}
    >
      <div
        style={{
          width: 72,
          height: 72,
          borderRadius: '50%',
          border: `4px solid ${theme.glassBorder}`,
          borderTopColor: theme.accent,
          animation: 'spin 0.9s linear infinite',
          boxShadow: `0 0 30px ${theme.accentSoft}`,
        }}
      />

      <div style={{ textAlign: 'center' }}>
        <p
          style={{
            fontSize: 18,
            fontWeight: 700,
            color: theme.primary,
            marginBottom: 8,
            letterSpacing: '-0.01em',
          }}
        >
          {message}
        </p>
        <p
          style={{
            fontSize: 13,
            color: theme.tertiary,
            letterSpacing: '0.02em',
          }}
        >
          Our AI is checking ingredients and safety data
        </p>
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
