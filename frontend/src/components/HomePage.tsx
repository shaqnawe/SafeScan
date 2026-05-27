import { useEffect, useState } from 'react'
import type { ScanHistoryEntry } from '../hooks/useScanHistory'
import {
  HeartPulse, ScanLine, Dna, Apple, Sparkles, Wheat, Clock, Search,
} from 'lucide-react'
import ThemeToggle from './ThemeToggle'
import { getTheme, glassStyle, FONT_STACK, FONT_DISPLAY } from '../theme'
import { searchProducts } from '../api'
import type { SearchResult } from '../types'

interface HomePageProps {
  onStartScanning:     () => void
  onSelectProduct:     (barcode: string) => void
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
  onSelectProduct,
  onViewHistory,
  onAllergenProfile,
  history,
  activeAllergenCount,
  isDark = false,
}: HomePageProps) {
  const theme = getTheme(isDark)

  const [searchQuery,   setSearchQuery]   = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [isSearching,   setIsSearching]   = useState(false)

  // Debounced fuzzy search via /api/search (pg_trgm). Cancels in-flight
  // requests on each keystroke via AbortController.
  useEffect(() => {
    const q = searchQuery.trim()
    if (q.length < 2) { setSearchResults([]); setIsSearching(false); return }
    const controller = new AbortController()
    const t = setTimeout(async () => {
      setIsSearching(true)
      try {
        const rows = await searchProducts(q, controller.signal)
        setSearchResults(rows)
      } catch (err) {
        if ((err as Error).name !== 'AbortError') setSearchResults([])
      } finally {
        setIsSearching(false)
      }
    }, 300)
    return () => { clearTimeout(t); controller.abort() }
  }, [searchQuery])

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

        {/* Divider — "or search by name" */}
        <div
          className="fade-up stagger-5"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            width: '100%',
            maxWidth: 320,
            margin: '24px auto 14px',
          }}
        >
          <div style={{ flex: 1, height: 1, background: theme.divider }} />
          <span
            style={{
              fontSize: 11,
              color: theme.tertiary,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              fontWeight: 600,
            }}
          >
            or
          </span>
          <div style={{ flex: 1, height: 1, background: theme.divider }} />
        </div>

        {/* Name / brand search */}
        <div
          className="fade-up stagger-5"
          style={{ width: '100%', maxWidth: 380, position: 'relative' }}
        >
          <Search
            size={16}
            strokeWidth={2}
            aria-hidden
            style={{
              position: 'absolute',
              left: 16,
              top: '50%',
              transform: 'translateY(-50%)',
              color: theme.tertiary,
              pointerEvents: 'none',
            }}
          />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search by name or brand…"
            style={{
              ...glassStyle(theme),
              width: '100%',
              padding: '14px 16px 14px 42px',
              borderRadius: 14,
              fontSize: 15,
              color: theme.primary,
              outline: 'none',
              boxSizing: 'border-box',
              fontFamily: FONT_STACK,
              boxShadow: 'none',
            }}
          />
        </div>

        {/* Results list */}
        {searchQuery.trim().length >= 2 && (
          <div
            style={{
              width: '100%',
              maxWidth: 380,
              marginTop: 10,
              maxHeight: 320,
              overflowY: 'auto',
              ...glassStyle(theme),
              borderRadius: 14,
              padding: 4,
              boxShadow: theme.ctaShadow,
            }}
          >
            {isSearching && searchResults.length === 0 && (
              <div style={{ padding: 16, color: theme.tertiary, fontSize: 13, textAlign: 'center' }}>
                Searching…
              </div>
            )}
            {!isSearching && searchResults.length === 0 && (
              <div style={{ padding: 16, color: theme.tertiary, fontSize: 13, textAlign: 'center' }}>
                No products match "{searchQuery.trim()}"
              </div>
            )}
            {searchResults.map(r => (
              <button
                key={r.barcode}
                onClick={() => onSelectProduct(r.barcode)}
                className="press"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  width: '100%',
                  padding: '10px 12px',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: 10,
                  cursor: 'pointer',
                  textAlign: 'left',
                  fontFamily: 'inherit',
                  color: theme.primary,
                }}
              >
                {r.image_url ? (
                  <img
                    src={r.image_url}
                    alt=""
                    style={{
                      width: 36, height: 36, borderRadius: 8, objectFit: 'contain',
                      background: theme.ingredientBg, flexShrink: 0, padding: 2,
                      border: `1px solid ${theme.glassBorder}`,
                    }}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                ) : (
                  <div style={{
                    width: 36, height: 36, borderRadius: 8,
                    background: theme.ingredientBg, flexShrink: 0,
                    border: `1px solid ${theme.glassBorder}`,
                  }} />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  {r.brand && (
                    <div style={{
                      fontSize: 10, fontWeight: 700, letterSpacing: '0.12em',
                      textTransform: 'uppercase', color: theme.tertiary,
                    }}>
                      {r.brand}
                    </div>
                  )}
                  <div style={{
                    fontSize: 13, fontWeight: 500, color: theme.primary, marginTop: 2,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {r.name}
                  </div>
                </div>
                <span style={{
                  fontSize: 10, color: theme.tertiary,
                  textTransform: 'uppercase', letterSpacing: '0.1em', flexShrink: 0,
                }}>
                  {r.product_type}
                </span>
              </button>
            ))}
          </div>
        )}
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
