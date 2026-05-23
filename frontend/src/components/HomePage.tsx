import type { ScanHistoryEntry } from '../hooks/useScanHistory'
import { getTheme, glassStyle, FONT_STACK, FONT_DISPLAY } from '../theme'

interface HomePageProps {
  onStartScanning:     () => void
  onViewHistory:       () => void
  onAllergenProfile:   () => void
  history:             ScanHistoryEntry[]
  activeAllergenCount: number
  isDark?:             boolean
}

const FEATURES = [
  {
    emoji: '🧬',
    title: 'Ingredient Analysis',
    desc:  '2M+ products cross-referenced against EU safety regulations',
  },
  {
    emoji: '🍎',
    title: 'Food Safety',
    desc:  'Nutri-Score, NOVA processing level, additives and allergens',
  },
  {
    emoji: '✨',
    title: 'Cosmetic Safety',
    desc:  'Parabens, endocrine disruptors, banned EU substances',
  },
]

export default function HomePage({
  onStartScanning,
  onViewHistory,
  onAllergenProfile,
  history,
  activeAllergenCount,
  isDark = false,
}: HomePageProps) {
  const theme = getTheme(isDark)

  return (
    <div
      style={{
        minHeight: '100vh',
        background: theme.bg,
        backgroundImage: theme.bgGradient,
        color: theme.primary,
        display: 'flex',
        flexDirection: 'column',
        overflowX: 'hidden',
        fontFamily: FONT_STACK,
        WebkitFontSmoothing: 'antialiased',
      }}
    >
      {/* Top-right pill buttons */}
      <div
        style={{
          position: 'fixed',
          top: 20,
          right: 20,
          zIndex: 10,
          display: 'flex',
          gap: 8,
        }}
      >
        <button
          onClick={onAllergenProfile}
          style={{
            ...glassStyle(theme),
            borderRadius: 999,
            padding: '8px 14px',
            color: activeAllergenCount > 0 ? theme.accent : theme.secondary,
            border: `1px solid ${activeAllergenCount > 0 ? theme.accent + '66' : theme.glassBorder}`,
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            boxShadow: 'none',
          }}
        >
          <span>🌾</span>
          <span>
            {activeAllergenCount > 0
              ? `${activeAllergenCount} allergen${activeAllergenCount !== 1 ? 's' : ''}`
              : 'Allergens'}
          </span>
        </button>

        {history.length > 0 && (
          <button
            onClick={onViewHistory}
            style={{
              ...glassStyle(theme),
              borderRadius: 999,
              padding: '8px 14px',
              color: theme.secondary,
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              boxShadow: 'none',
            }}
          >
            <span>🕐</span>
            <span>
              {history.length} scan{history.length !== 1 ? 's' : ''}
            </span>
          </button>
        )}
      </div>

      {/* Hero */}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          padding: '88px 32px 48px',
          maxWidth: 480,
          width: '100%',
          margin: '0 auto',
        }}
      >
        {/* Logo tile */}
        <div
          style={{
            width: 88,
            height: 88,
            borderRadius: 24,
            background: theme.gradeGradient,
            display: 'grid',
            placeItems: 'center',
            fontSize: 42,
            marginBottom: 24,
            boxShadow: theme.ctaShadow,
          }}
        >
          🔍
        </div>

        {/* Wordmark — Fraunces display face, optical-size large, italic for character.
            Horizontal padding gives the italic 'n' exit stroke room inside the
            background-clip: text mask (otherwise the trailing glyph is chopped). */}
        <h1
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 56,
            fontWeight: 500,
            fontStyle: 'italic',
            fontVariationSettings: '"opsz" 144, "SOFT" 50',
            letterSpacing: '-0.035em',
            marginBottom: 12,
            padding: '0 0.18em',
            background: isDark
              ? 'linear-gradient(135deg, #fafafa 40%, #fbbf24 100%)'
              : 'linear-gradient(135deg, #1a1a1f 40%, #d97706 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            lineHeight: 1,
          }}
        >
          SafeScan
        </h1>

        {/* Tagline */}
        <p
          style={{
            fontSize: 17,
            color: theme.tertiary,
            lineHeight: 1.5,
            maxWidth: 300,
            marginBottom: 40,
          }}
        >
          Scan any product. Know exactly what&apos;s inside.
        </p>

        {/* Primary CTA */}
        <button
          onClick={onStartScanning}
          style={{
            padding: '18px 48px',
            borderRadius: 18,
            border: 'none',
            background: theme.gradeGradient,
            color: theme.btnText,
            fontSize: 17,
            fontWeight: 700,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            boxShadow: theme.ctaShadow,
            letterSpacing: '-0.01em',
            fontFamily: FONT_STACK,
          }}
        >
          <span style={{ fontSize: 20 }}>📷</span>
          <span>Start Scanning</span>
        </button>

        <p
          style={{
            marginTop: 16,
            fontSize: 12,
            color: theme.tertiary,
            letterSpacing: '0.05em',
          }}
        >
          Point at a barcode — results in seconds
        </p>
      </div>

      {/* Feature glass cards */}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          padding: '0 20px 48px',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          maxWidth: 480,
          width: '100%',
          margin: '0 auto',
          boxSizing: 'border-box',
        }}
      >
        {FEATURES.map(f => (
          <div
            key={f.title}
            style={{
              ...glassStyle(theme),
              borderRadius: 18,
              padding: '18px 20px',
              display: 'flex',
              alignItems: 'center',
              gap: 16,
            }}
          >
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 12,
                background: theme.accentSoft,
                border: `1px solid ${theme.accent}40`,
                display: 'grid',
                placeItems: 'center',
                fontSize: 22,
                flexShrink: 0,
              }}
            >
              {f.emoji}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p
                style={{
                  fontSize: 15,
                  fontWeight: 700,
                  color: theme.primary,
                  marginBottom: 3,
                  letterSpacing: '-0.01em',
                }}
              >
                {f.title}
              </p>
              <p
                style={{
                  fontSize: 13,
                  color: theme.tertiary,
                  lineHeight: 1.4,
                }}
              >
                {f.desc}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          textAlign: 'center',
          padding: '0 20px 40px',
          marginTop: 'auto',
        }}
      >
        <p
          style={{
            fontSize: 12,
            color: theme.tertiary,
            opacity: 0.7,
            lineHeight: 1.6,
            letterSpacing: '0.02em',
          }}
        >
          Powered by Claude AI · EU ingredient database · Open Food Facts
        </p>
      </div>
    </div>
  )
}
