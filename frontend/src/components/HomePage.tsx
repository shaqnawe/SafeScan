import { useEffect, useState } from 'react'
import type { ScanHistoryEntry } from '../hooks/useScanHistory'
import {
  ScanLine, Dna, Apple, Sparkles, Wheat, Clock, Search,
} from 'lucide-react'
import ThemeToggle from './ThemeToggle'
import { getTheme, glassStyle, FONT_STACK } from '../theme'
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
        {/* Wordmark — designer-supplied SVG inlined so the four neutral colors
            (brand text, tagline, divider, rule) can adapt to dark mode via
            theme values. Brand colors (terracotta hex + green sprout) stay
            fixed because they're brand identity. The canonical SVG file at
            /public/ingrediq-wordmark.svg keeps its hardcoded light-mode
            colors for share-card / social-preview / non-React contexts. */}
        <h1
          className="fade-up stagger-1"
          style={{
            margin: '8px 0 16px',
            lineHeight: 0,
          }}
          aria-label="IngrediQ"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 310 80"
            role="img"
            aria-label="IngrediQ — Health, Food, Cosmetics"
            style={{
              width: 'min(320px, 80vw)',
              height: 'auto',
              display: 'block',
            }}
          >
            {/* Hex icon */}
            <polygon points="74,40 57,69 23,69 6,40 23,11 57,11" fill="none" stroke="#C4603A" strokeWidth="1.6" />
            <polygon points="60,40 50,57 30,57 20,40 30,23 50,23" fill="none" stroke="#C4603A" strokeWidth="0.6" opacity="0.4" />
            <circle cx="74" cy="40" r="3" fill="#E8A870" />
            <circle cx="57" cy="69" r="3" fill="#E8A870" />
            <circle cx="23" cy="69" r="3" fill="#E8A870" />
            <circle cx="6"  cy="40" r="3" fill="#E8A870" />
            <circle cx="23" cy="11" r="3" fill="#E8A870" />
            <circle cx="57" cy="11" r="3" fill="#E8A870" />
            {/* Sprout */}
            <line x1="40" y1="54" x2="40" y2="27" stroke="#7A9E50" strokeWidth="2.2" strokeLinecap="round" />
            <path d="M40 46 C33 41 26 43 25 48 C30 51 38 49 40 46 Z" fill="#7A9E50" />
            <path d="M40 36 C47 31 54 33 55 38 C50 41 42 39 40 36 Z" fill="#7A9E50" />
            <circle cx="40" cy="27" r="3" fill="#7A9E50" />
            {/* Vertical divider — theme-aware */}
            <line x1="92" y1="18" x2="92" y2="62" stroke={theme.glassBorder} strokeWidth="1" />
            {/* Brand name */}
            <text x="104" y="38" fontSize="22" fontWeight="500" letterSpacing="1.5" fill={theme.primary} fontFamily="'Helvetica Neue', Helvetica, Arial, sans-serif">IngrediQ</text>
            {/* Thin rule */}
            <line x1="104" y1="46" x2="300" y2="46" stroke={theme.divider} strokeWidth="0.5" />
            {/* Tagline */}
            <text x="104" y="60" fontSize="9" letterSpacing="1" fill={theme.tertiary} fontFamily="'Helvetica Neue', Helvetica, Arial, sans-serif">HEALTH · FOOD · COSMETICS</text>
          </svg>
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
