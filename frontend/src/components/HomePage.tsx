import type { ScanHistoryEntry } from '../hooks/useScanHistory'
import {
  HeartPulse, ScanLine, Dna, Apple, Sparkles, Wheat, Clock,
} from 'lucide-react'
import ThemeToggle from './ThemeToggle'
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
    Icon:  Dna,
    title: 'Ingredient Analysis',
    desc:  '2M+ products cross-referenced against EU safety regulations',
  },
  {
    Icon:  Apple,
    title: 'Food Safety',
    desc:  'Nutri-Score, NOVA processing level, additives and allergens',
  },
  {
    Icon:  Sparkles,
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
        position: 'relative',
      }}
    >
      {/* Anchor — giant ghosted wordmark behind the hero.
          Sits below the logo tile, breaks the centered axis, extends into the gutters.
          Pointer-events:none so it never intercepts taps. */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          top: 200,
          left: '50%',
          transform: 'translateX(-50%) rotate(-3deg)',
          fontFamily: FONT_DISPLAY,
          fontSize: 240,
          fontWeight: 400,
          fontStyle: 'italic',
          fontVariationSettings: '"opsz" 144, "SOFT" 70',
          letterSpacing: '-0.06em',
          lineHeight: 0.85,
          color: theme.primary,
          opacity: isDark ? 0.035 : 0.05,
          pointerEvents: 'none',
          userSelect: 'none',
          whiteSpace: 'nowrap',
          zIndex: 0,
        }}
      >
        SafeScan
      </div>

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
        <ThemeToggle />

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
          <Wheat size={15} strokeWidth={2} aria-hidden />
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
            <Clock size={15} strokeWidth={2} aria-hidden />
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
        {/* Logo tile — HeartPulse signals "health" / "safety analysis" */}
        <div
          className="fade-up stagger-1"
          style={{
            width: 88,
            height: 88,
            borderRadius: 24,
            background: theme.gradeGradient,
            display: 'grid',
            placeItems: 'center',
            marginBottom: 24,
            boxShadow: theme.ctaShadow,
            color: theme.btnText,
          }}
        >
          <HeartPulse size={44} strokeWidth={2.25} aria-hidden />
        </div>

        {/* Wordmark — Fraunces display face, optical-size large, italic for character.
            Horizontal padding gives the italic 'n' exit stroke room inside the
            background-clip: text mask (otherwise the trailing glyph is chopped). */}
        <h1
          className="fade-up stagger-2"
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
          className="fade-up stagger-3"
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
          className="fade-up stagger-4 press"
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
          <ScanLine size={20} strokeWidth={2.25} aria-hidden />
          <span>Scan a Product</span>
        </button>

        <p
          className="fade-up stagger-5"
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
        {FEATURES.map((f, i) => (
          <div
            key={f.title}
            className={`fade-up lift stagger-${5 + i}`}
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
                flexShrink: 0,
                color: theme.accent,
              }}
            >
              <f.Icon size={22} strokeWidth={2} aria-hidden />
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
