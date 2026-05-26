import type { SafetyReport, IngredientAnalysis, RecallAlert } from '../types'
import { ArrowLeft } from 'lucide-react'
import { matchAllergens } from '../hooks/useAllergenProfile'
import type { AllergenInfo } from '../hooks/useAllergenProfile'
import ThemeToggle from './ThemeToggle'
import {
  getTheme,
  gradeGradient,
  SAFETY_INDICATOR,
  glassStyle,
  FONT_STACK,
  FONT_DISPLAY,
  type Theme,
} from '../theme'

interface SafetyReportProps {
  report: SafetyReport
  onScanAgain: () => void
  isDark?: boolean
  activeAllergens?: AllergenInfo[]
}

// ──────────────────────────────────────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────────────────────────────────────

function Glass({
  children,
  style,
  theme,
  className,
}: {
  children: React.ReactNode
  style?: React.CSSProperties
  theme: Theme
  className?: string
}) {
  return (
    <div
      className={className}
      style={{
        ...glassStyle(theme),
        padding: 24,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

function SectionLabel({
  children,
  theme,
}: {
  children: React.ReactNode
  theme: Theme
}) {
  return (
    <h2
      style={{
        fontSize: 11,
        letterSpacing: '0.2em',
        textTransform: 'uppercase',
        color: theme.tertiary,
        fontWeight: 700,
        marginBottom: 16,
      }}
    >
      {children}
    </h2>
  )
}

function Indicator({ level }: { level: string }) {
  const config = SAFETY_INDICATOR[level] || SAFETY_INDICATOR.caution
  return (
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: config.color,
        boxShadow: `0 0 12px ${config.glow}`,
        flexShrink: 0,
        display: 'inline-block',
      }}
    />
  )
}

// Concern tags considered "severe" — render in red rather than neutral.
const SEVERE_TAGS = new Set<string>([
  'iarc_group_1', 'iarc_group_2a', 'iarc_group_2b', 'carcinogen',
  'ghs_carcinogen_cat1', 'ghs_carcinogen_cat2',
  'ghs_reproductive_toxin', 'ghs_mutagen',
  'prop65_carcinogen', 'prop65_developmental_toxin', 'prop65_reproductive_toxin',
  'endocrine_disruptor', 'formaldehyde_releaser', 'neurotoxin',
])

function prettyTag(tag: string): string {
  return tag
    .replace(/_/g, ' ')
    .replace(/\biarc\b/i, 'IARC')
    .replace(/\bghs\b/i, 'GHS')
    .replace(/\bprop65\b/i, 'Prop 65')
    .replace(/\bsls\b/i, 'SLS')
    .replace(/\bsles\b/i, 'SLES')
    .replace(/\bcat(\d)\b/i, 'cat. $1')
    .replace(/\bgroup (\d[ab]?)\b/i, (_, g) => `Group ${g.toUpperCase()}`)
    .replace(/^\w/, c => c.toUpperCase())
}

const SOURCE_LABELS: Record<string, string> = {
  efsa:                                'EFSA',
  cosing:                              'CosIng',
  iarc:                                'IARC',
  ifra:                                'IFRA',
  echa:                                'ECHA',
  fda:                                 'FDA',
  scientific_committee_on_consumer_safety: 'SCCS',
  eu_regulation_1333_2008:             'EU 1333/2008',
  eu_regulation_1223_2009:             'EU 1223/2009',
  prop65:                              'Prop 65',
  'prop 65':                           'Prop 65',
  'claude classification':             'Claude',
}

function prettySource(src: string): string {
  const key = src.toLowerCase().trim()
  return SOURCE_LABELS[key] ?? src.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function ConcernChip({ tag, theme }: { tag: string; theme: Theme }) {
  const severe = SEVERE_TAGS.has(tag)
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: '0.02em',
        padding: '3px 8px',
        borderRadius: 999,
        background: severe ? 'rgba(239,68,68,0.12)' : theme.ingredientBg,
        color: severe ? '#ef4444' : theme.secondary,
        border: `1px solid ${severe ? 'rgba(239,68,68,0.3)' : theme.ingredientBorder}`,
        whiteSpace: 'nowrap',
      }}
    >
      {prettyTag(tag)}
    </span>
  )
}

function IngredientRow({
  ingredient,
  theme,
}: {
  ingredient: IngredientAnalysis
  theme: Theme
}) {
  const tags    = ingredient.concerns ?? []
  const sources = ingredient.sources ?? []
  const impact  = ingredient.score_impact

  return (
    <div
      style={{
        display: 'flex',
        gap: 12,
        padding: '14px 16px',
        background: theme.ingredientBg,
        borderRadius: 12,
        marginBottom: 8,
        border: `1px solid ${theme.ingredientBorder}`,
        alignItems: 'flex-start',
      }}
    >
      <div style={{ paddingTop: 4 }}>
        <Indicator level={ingredient.safety_level} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
          }}
        >
          <div
            style={{
              fontSize: 14,
              color: theme.primary,
              fontWeight: 500,
              flex: 1,
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {ingredient.name}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {typeof impact === 'number' && impact < 0 && (
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  color: '#ef4444',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {impact} pts
              </span>
            )}
            <span
              style={{
                fontSize: 10,
                color: theme.tertiary,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                fontWeight: 600,
              }}
            >
              {ingredient.safety_level}
            </span>
          </div>
        </div>

        {ingredient.concern && (
          <div
            style={{
              fontSize: 12,
              color: theme.tertiary,
              marginTop: 4,
              lineHeight: 1.4,
            }}
          >
            {ingredient.concern}
          </div>
        )}

        {tags.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
            {tags.map(t => (
              <ConcernChip key={t} tag={t} theme={theme} />
            ))}
          </div>
        )}

        {sources.length > 0 && (
          <div
            style={{
              fontSize: 10,
              color: theme.tertiary,
              marginTop: 8,
              letterSpacing: '0.04em',
            }}
          >
            Sources: {sources.map(prettySource).join(' · ')}
          </div>
        )}
      </div>
    </div>
  )
}

function PointRow({
  point,
  type,
  theme,
}: {
  point: string
  type: 'pos' | 'neg'
  theme: Theme
}) {
  const isPos = type === 'pos'
  return (
    <div
      style={{
        display: 'flex',
        gap: 12,
        padding: '10px 0',
        fontSize: 14,
        color: theme.secondary,
        borderBottom: `1px solid ${theme.divider}`,
        alignItems: 'flex-start',
      }}
    >
      <span
        style={{
          width: 22,
          height: 22,
          borderRadius: '50%',
          display: 'grid',
          placeItems: 'center',
          fontSize: 12,
          fontWeight: 700,
          flexShrink: 0,
          background: isPos ? 'rgba(34,197,94,0.15)' : 'rgba(245,158,11,0.15)',
          color: isPos ? '#22c55e' : theme.accent,
        }}
      >
        {isPos ? '+' : '!'}
      </span>
      <span style={{ lineHeight: 1.4 }}>{point}</span>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────────────────────────────────────

export default function SafetyReportView({
  report,
  onScanAgain,
  isDark = false,
  activeAllergens = [],
}: SafetyReportProps) {
  const theme = getTheme(isDark)

  // ── Not-found state ────────────────────────────────────────────────────────
  if (report.not_found) {
    return (
      <div
        style={{
          minHeight: '100vh',
          background: theme.bg,
          backgroundImage: theme.bgGradient,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
        }}
      >
        <Glass theme={theme} style={{ maxWidth: 400, width: '100%', textAlign: 'center', padding: 40 }}>
          <div style={{ fontSize: 56, marginBottom: 16 }}>🔍</div>
          <h2
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: theme.primary,
              marginBottom: 10,
              letterSpacing: '-0.02em',
            }}
          >
            Product Not Found
          </h2>
          <p
            style={{
              fontSize: 15,
              color: theme.tertiary,
              lineHeight: 1.6,
              marginBottom: 24,
            }}
          >
            We couldn&apos;t find barcode{' '}
            <strong style={{ color: theme.primary, fontFamily: 'monospace' }}>{report.barcode}</strong> in our
            databases. Try another product or check the barcode.
          </p>
          <button
            onClick={onScanAgain}
            style={{
              width: '100%',
              padding: 16,
              borderRadius: 14,
              border: 'none',
              background: theme.gradeGradient,
              color: theme.btnText,
              fontSize: 15,
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: theme.ctaShadow,
            }}
          >
            Scan Another Product
          </button>
        </Glass>
      </div>
    )
  }

  // ── Stats ──────────────────────────────────────────────────────────────────
  const safeCount    = report.ingredients_analysis.filter(i => i.safety_level === 'safe').length
  const cautionCount = report.ingredients_analysis.filter(i => i.safety_level === 'caution').length
  const avoidCount   = report.ingredients_analysis.filter(i => i.safety_level === 'avoid').length

  const allIngredientNames = report.ingredients_analysis.map(i => i.name)
  const allergenMatches = matchAllergens(allIngredientNames, activeAllergens)
  const triggeredAllergens = activeAllergens.filter(a => allergenMatches.has(a.id))

  const statItems = [
    { count: safeCount,    label: 'Safe',    color: '#22c55e' },
    { count: cautionCount, label: 'Caution', color: theme.accent },
    { count: avoidCount,   label: 'Avoid',   color: '#ef4444' },
  ]

  return (
    <div
      style={{
        minHeight: '100vh',
        background: theme.bg,
        backgroundImage: theme.bgGradient,
        color: theme.primary,
        paddingBottom: 110,
        fontFamily: FONT_STACK,
        WebkitFontSmoothing: 'antialiased',
      }}
    >
      <div style={{ maxWidth: 480, margin: '0 auto', padding: '32px 20px 0' }}>
        {/* Top bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 24,
          }}
        >
          <button
            onClick={onScanAgain}
            className="press"
            style={{
              width: 36,
              height: 36,
              borderRadius: 12,
              border: `1px solid ${theme.glassBorder}`,
              background: theme.glass,
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              color: theme.primary,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            aria-label="Back"
          >
            <ArrowLeft size={16} strokeWidth={2} aria-hidden />
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 12, color: theme.tertiary }}>Just now</span>
            <ThemeToggle variant="icon" />
          </div>
        </div>

        {/* Hero — product card */}
        <Glass theme={theme} className="fade-up stagger-1" style={{ textAlign: 'center', marginBottom: 16 }}>
          {report.image_url && (
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: 16,
                overflow: 'hidden',
                margin: '0 auto 16px',
                background: theme.ingredientBg,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: `1px solid ${theme.glassBorder}`,
              }}
            >
              <img
                src={report.image_url}
                alt={report.product_name}
                style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 4 }}
                onError={e => {
                  (e.target as HTMLImageElement).style.display = 'none'
                }}
              />
            </div>
          )}
          <div
            style={{
              fontSize: 11,
              letterSpacing: '0.2em',
              textTransform: 'uppercase',
              color: theme.accent,
              fontWeight: 700,
              marginBottom: 8,
            }}
          >
            {report.brand || 'Unknown brand'} · {report.product_type}
          </div>
          <div
            style={{
              fontSize: 22,
              fontWeight: 700,
              letterSpacing: '-0.02em',
              color: theme.primary,
              marginBottom: 24,
              lineHeight: 1.2,
            }}
          >
            {report.product_name || 'Unknown Product'}
          </div>

          {/* Grade display */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 24,
              padding: '8px 0',
            }}
          >
            <div
              style={{
                fontFamily: FONT_DISPLAY,
                fontSize: 120,
                fontWeight: 300,
                fontVariationSettings: '"opsz" 144, "SOFT" 30',
                letterSpacing: '-0.06em',
                background: gradeGradient(report.grade, isDark),
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
                lineHeight: 0.85,
              }}
            >
              {report.grade}
            </div>
            <div style={{ width: 1, height: 80, background: theme.glassBorder }} />
            <div style={{ textAlign: 'left' }}>
              <div>
                <span style={{ fontSize: 36, fontWeight: 700, color: theme.primary, lineHeight: 1 }}>
                  {report.score}
                </span>
                <span style={{ fontSize: 16, color: theme.tertiary }}>/100</span>
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: theme.tertiary,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  marginTop: 6,
                }}
              >
                Safety Score
              </div>
            </div>
          </div>
        </Glass>

        {/* Allergen warning banner */}
        {triggeredAllergens.length > 0 && (
          <Glass
            theme={theme}
            style={{
              borderColor: 'rgba(239,68,68,0.4)',
              background: isDark ? 'rgba(127,29,29,0.3)' : 'rgba(254,226,226,0.7)',
              marginBottom: 16,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <span style={{ fontSize: 18 }}>⚠️</span>
              <span style={{ fontSize: 15, fontWeight: 700, color: '#ef4444' }}>Allergen Alert</span>
            </div>
            <div style={{ fontSize: 13, color: theme.secondary, marginBottom: 12, lineHeight: 1.4 }}>
              This product may contain allergens from your profile:
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {triggeredAllergens.map(a => (
                <span
                  key={a.id}
                  style={{
                    background: 'rgba(239,68,68,0.15)',
                    border: '1px solid rgba(239,68,68,0.3)',
                    borderRadius: 999,
                    padding: '4px 12px',
                    fontSize: 13,
                    fontWeight: 600,
                    color: '#ef4444',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                  }}
                >
                  <span>{a.emoji}</span>
                  <span>{a.label}</span>
                </span>
              ))}
            </div>
          </Glass>
        )}

        {/* Recall alert banner */}
        {report.recalls && report.recalls.length > 0 && (
          <Glass
            theme={theme}
            style={{
              borderColor: 'rgba(239,68,68,0.5)',
              background: isDark ? 'rgba(127,29,29,0.4)' : 'rgba(254,226,226,0.8)',
              marginBottom: 16,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <span style={{ fontSize: 20 }}>🚨</span>
              <span style={{ fontSize: 15, fontWeight: 700, color: '#ef4444' }}>
                Active Recall Alert
              </span>
            </div>
            <div style={{ fontSize: 13, color: theme.secondary, marginBottom: 12, lineHeight: 1.4 }}>
              This product may be subject to an EU food safety recall. Do not consume and check the official
              notice.
            </div>
            {report.recalls.map((recall: RecallAlert, i: number) => (
              <div
                key={i}
                style={{
                  background: 'rgba(239,68,68,0.08)',
                  border: '1px solid rgba(239,68,68,0.25)',
                  borderRadius: 12,
                  padding: '12px 14px',
                  marginBottom: i < report.recalls.length - 1 ? 8 : 0,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 600, color: theme.primary, marginBottom: 6 }}>
                  {recall.title}
                </div>
                {recall.risk_level && (
                  <span
                    style={{
                      display: 'inline-block',
                      background:
                        recall.risk_level === 'serious' || recall.risk_level === 'high'
                          ? '#ef4444'
                          : theme.accent,
                      color: '#fff',
                      fontSize: 11,
                      fontWeight: 700,
                      borderRadius: 6,
                      padding: '2px 8px',
                      textTransform: 'uppercase',
                      marginBottom: 4,
                    }}
                  >
                    {recall.risk_level} risk
                  </span>
                )}
                {recall.published_at && (
                  <div style={{ fontSize: 11, color: theme.tertiary, marginBottom: recall.link ? 6 : 0 }}>
                    {new Date(recall.published_at).toLocaleDateString()}
                  </div>
                )}
                {recall.link && (
                  <a
                    href={recall.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: 12, color: '#ef4444', fontWeight: 600 }}
                  >
                    View official notice →
                  </a>
                )}
              </div>
            ))}
          </Glass>
        )}

        {/* Summary */}
        <Glass theme={theme} className="fade-up stagger-2" style={{ marginBottom: 16 }}>
          <SectionLabel theme={theme}>Summary</SectionLabel>
          <div style={{ fontSize: 15, color: theme.secondary, lineHeight: 1.5 }}>{report.summary}</div>
        </Glass>

        {/* Ingredient stats */}
        {report.ingredients_analysis.length > 0 && (
          <Glass theme={theme} className="fade-up stagger-3" style={{ marginBottom: 16 }}>
            <SectionLabel theme={theme}>Ingredient Overview</SectionLabel>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {statItems.map(({ count, label, color }) => (
                <div
                  key={label}
                  style={{
                    padding: 14,
                    borderRadius: 12,
                    background: theme.ingredientBg,
                    border: `1px solid ${theme.ingredientBorder}`,
                    textAlign: 'center',
                  }}
                >
                  <div style={{ fontSize: 26, fontWeight: 700, color, lineHeight: 1 }}>{count}</div>
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: theme.tertiary,
                      letterSpacing: '0.08em',
                      textTransform: 'uppercase',
                      marginTop: 6,
                    }}
                  >
                    {label}
                  </div>
                </div>
              ))}
            </div>
          </Glass>
        )}

        {/* Findings */}
        {(report.positive_points.length > 0 || report.negative_points.length > 0) && (
          <Glass theme={theme} className="fade-up stagger-4" style={{ marginBottom: 16 }}>
            <SectionLabel theme={theme}>Findings</SectionLabel>
            <div>
              {report.positive_points.map((p, i) => (
                <PointRow key={`p-${i}`} point={p} type="pos" theme={theme} />
              ))}
              {report.negative_points.map((p, i) => (
                <PointRow key={`n-${i}`} point={p} type="neg" theme={theme} />
              ))}
            </div>
          </Glass>
        )}

        {/* Ingredients */}
        {report.ingredients_analysis.length > 0 && (
          <Glass theme={theme} className="fade-up stagger-5" style={{ marginBottom: 16 }}>
            <SectionLabel theme={theme}>
              Ingredients · {report.ingredients_analysis.length}
            </SectionLabel>
            {(['avoid', 'caution', 'safe'] as const).map(level => {
              const items = report.ingredients_analysis.filter(i => i.safety_level === level)
              if (items.length === 0) return null
              return items.map((ing, i) => (
                <IngredientRow key={`${level}-${i}`} ingredient={ing} theme={theme} />
              ))
            })}
          </Glass>
        )}

        {/* Barcode footer */}
        <Glass
          theme={theme}
          style={{
            padding: '14px 18px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ fontSize: 13, color: theme.tertiary }}>Barcode</span>
          <span style={{ fontSize: 13, fontWeight: 600, color: theme.primary, fontFamily: 'monospace' }}>
            {report.barcode}
          </span>
        </Glass>
      </div>

      {/* Fixed CTA */}
      <div
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          padding: '16px 20px 28px',
          background: theme.ctaWrapBg,
        }}
      >
        <button
          onClick={onScanAgain}
          className="press"
          style={{
            display: 'block',
            width: '100%',
            maxWidth: 440,
            margin: '0 auto',
            background: theme.gradeGradient,
            color: theme.btnText,
            border: 'none',
            padding: 16,
            borderRadius: 14,
            fontSize: 15,
            fontWeight: 700,
            cursor: 'pointer',
            boxShadow: theme.ctaShadow,
            letterSpacing: '-0.01em',
            fontFamily: FONT_STACK,
          }}
        >
          Scan Another Product
        </button>
      </div>
    </div>
  )
}
