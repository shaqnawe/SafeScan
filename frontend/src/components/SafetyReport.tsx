import type { SafetyReport, IngredientAnalysis, RecallAlert } from '../types'
import { matchAllergens } from '../hooks/useAllergenProfile'
import type { AllergenInfo } from '../hooks/useAllergenProfile'

interface SafetyReportProps {
  report: SafetyReport
  onScanAgain: () => void
  isDark?: boolean
  activeAllergens?: AllergenInfo[]
}

const GRADE_CONFIG = {
  A: { bg: '#34c759', light: '#e8f8ed', darkLight: '#0d3320', label: 'Excellent' },
  B: { bg: '#a3d977', light: '#f0f7e6', darkLight: '#1e3310', label: 'Good' },
  C: { bg: '#ff9f0a', light: '#fff4e0', darkLight: '#332500', label: 'Average' },
  D: { bg: '#ff3b30', light: '#ffe8e6', darkLight: '#330d0a', label: 'Poor' },
  E: { bg: '#9c2b2b', light: '#f5e0e0', darkLight: '#2e1515', label: 'Very Poor' },
}

const SAFETY_COLORS = {
  safe:    { light: { bg: '#e8f8ed', text: '#1a7a35', dot: '#34c759' }, dark: { bg: '#0d3320', text: '#4cd964', dot: '#34c759' } },
  caution: { light: { bg: '#fff4e0', text: '#7a4800', dot: '#ff9f0a' }, dark: { bg: '#332500', text: '#ff9f0a', dot: '#ff9f0a' } },
  avoid:   { light: { bg: '#ffe8e6', text: '#7a1a15', dot: '#ff3b30' }, dark: { bg: '#330d0a', text: '#ff453a', dot: '#ff3b30' } },
}

function GradeCircle({ grade, score, isDark }: { grade: string; score: number; isDark: boolean }) {
  const config = GRADE_CONFIG[grade as keyof typeof GRADE_CONFIG] || GRADE_CONFIG.E
  const circumference = 2 * Math.PI * 44
  const offset = circumference - (score / 100) * circumference
  const badgeBg = isDark ? config.darkLight : config.light

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
      <div style={{ position: 'relative', width: '110px', height: '110px' }}>
        <svg width="110" height="110" style={{ transform: 'rotate(-90deg)' }}>
          <circle
            cx="55" cy="55" r="44"
            fill="none"
            stroke={isDark ? '#3a3a3c' : '#e5e5ea'}
            strokeWidth="8"
          />
          <circle
            cx="55" cy="55" r="44"
            fill="none"
            stroke={config.bg}
            strokeWidth="8"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 1s ease' }}
          />
        </svg>
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <span style={{
            fontSize: '36px',
            fontWeight: '800',
            color: config.bg,
            lineHeight: 1,
          }}>
            {grade}
          </span>
          <span style={{
            fontSize: '12px',
            color: '#8e8e93',
            fontWeight: '500',
          }}>
            {score}/100
          </span>
        </div>
      </div>
      <span style={{
        fontSize: '13px',
        fontWeight: '600',
        color: config.bg,
        background: badgeBg,
        padding: '4px 12px',
        borderRadius: '20px',
      }}>
        {config.label}
      </span>
    </div>
  )
}

function IngredientBadge({ ingredient, isDark }: { ingredient: IngredientAnalysis; isDark: boolean }) {
  const palette = SAFETY_COLORS[ingredient.safety_level as keyof typeof SAFETY_COLORS] || SAFETY_COLORS.caution
  const colors = isDark ? palette.dark : palette.light

  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-start',
      gap: '10px',
      padding: '12px',
      background: colors.bg,
      borderRadius: '10px',
      marginBottom: '8px',
    }}>
      <div style={{
        width: '8px',
        height: '8px',
        borderRadius: '50%',
        background: colors.dot,
        marginTop: '5px',
        flexShrink: 0,
      }} />
      <div>
        <p style={{
          fontSize: '14px',
          fontWeight: '600',
          color: colors.text,
          marginBottom: ingredient.concern ? '2px' : 0,
        }}>
          {ingredient.name}
        </p>
        {ingredient.concern && (
          <p style={{
            fontSize: '12px',
            color: colors.text,
            opacity: 0.8,
          }}>
            {ingredient.concern}
          </p>
        )}
      </div>
      <div style={{ marginLeft: 'auto', flexShrink: 0 }}>
        <span style={{
          fontSize: '11px',
          fontWeight: '600',
          color: colors.text,
          textTransform: 'capitalize',
          opacity: 0.8,
        }}>
          {ingredient.safety_level}
        </span>
      </div>
    </div>
  )
}

export default function SafetyReportView({ report, onScanAgain, isDark = false, activeAllergens = [] }: SafetyReportProps) {
  const bg = isDark ? '#000' : '#f5f5f7'
  const cardBg = isDark ? '#1c1c1e' : '#fff'
  const primaryText = isDark ? '#f2f2f7' : '#1c1c1e'
  const secondaryText = '#8e8e93'
  const cardShadow = isDark ? '0 1px 6px rgba(0,0,0,0.4)' : '0 1px 6px rgba(0,0,0,0.05)'
  const heroBorder = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)'
  const backBtnBg = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'
  const bottomGradient = isDark
    ? 'linear-gradient(to top, rgba(0,0,0,1) 80%, rgba(0,0,0,0))'
    : 'linear-gradient(to top, rgba(245,245,247,1) 80%, rgba(245,245,247,0))'
  const scanBtnBg = isDark ? '#f2f2f7' : '#1c1c1e'
  const scanBtnText = isDark ? '#1c1c1e' : '#fff'

  if (report.not_found) {
    return (
      <div style={{
        minHeight: '100vh',
        background: bg,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        gap: '20px',
      }}>
        <div style={{
          background: cardBg,
          borderRadius: '24px',
          padding: '40px 32px',
          textAlign: 'center',
          maxWidth: '400px',
          width: '100%',
          boxShadow: isDark ? '0 2px 20px rgba(0,0,0,0.4)' : '0 2px 20px rgba(0,0,0,0.06)',
        }}>
          <div style={{ fontSize: '56px', marginBottom: '16px' }}>🔍</div>
          <h2 style={{
            fontSize: '22px',
            fontWeight: '700',
            color: primaryText,
            marginBottom: '10px',
          }}>
            Product Not Found
          </h2>
          <p style={{
            fontSize: '15px',
            color: secondaryText,
            lineHeight: 1.6,
            marginBottom: '24px',
          }}>
            We couldn't find barcode <strong style={{ color: primaryText }}>{report.barcode}</strong> in our databases.
            Try another product or check the barcode.
          </p>
          <button
            onClick={onScanAgain}
            style={{
              width: '100%',
              padding: '16px',
              borderRadius: '14px',
              border: 'none',
              background: '#34c759',
              color: '#fff',
              fontSize: '16px',
              fontWeight: '600',
              cursor: 'pointer',
            }}
          >
            Scan Another Product
          </button>
        </div>
      </div>
    )
  }

  const grade = report.grade as keyof typeof GRADE_CONFIG
  const gradeConfig = GRADE_CONFIG[grade] || GRADE_CONFIG.E

  const safeCount = report.ingredients_analysis.filter(i => i.safety_level === 'safe').length
  const cautionCount = report.ingredients_analysis.filter(i => i.safety_level === 'caution').length
  const avoidCount = report.ingredients_analysis.filter(i => i.safety_level === 'avoid').length

  // Allergen matching
  const allIngredientNames = report.ingredients_analysis.map(i => i.name)
  const allergenMatches = matchAllergens(allIngredientNames, activeAllergens)
  const triggeredAllergens = activeAllergens.filter(a => allergenMatches.has(a.id))

  const statItems = [
    { count: safeCount,    label: 'Safe',    color: '#34c759', bg: isDark ? '#0d3320' : '#e8f8ed' },
    { count: cautionCount, label: 'Caution', color: '#ff9f0a', bg: isDark ? '#332500' : '#fff4e0' },
    { count: avoidCount,   label: 'Avoid',   color: '#ff3b30', bg: isDark ? '#330d0a' : '#ffe8e6' },
  ]

  return (
    <div style={{
      minHeight: '100vh',
      background: bg,
      paddingBottom: '100px',
    }}>
      {/* Hero section */}
      <div style={{
        background: `linear-gradient(160deg, ${gradeConfig.bg}22 0%, ${gradeConfig.bg}08 100%)`,
        borderBottom: `1px solid ${heroBorder}`,
        padding: '20px 20px 28px',
      }}>
        {/* Top bar */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          marginBottom: '20px',
        }}>
          <button
            onClick={onScanAgain}
            style={{
              background: backBtnBg,
              border: 'none',
              borderRadius: '50%',
              width: '36px',
              height: '36px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              fontSize: '16px',
              color: primaryText,
            }}
          >
            ←
          </button>
          <span style={{
            flex: 1,
            textAlign: 'center',
            fontSize: '15px',
            fontWeight: '600',
            color: primaryText,
            marginRight: '36px',
          }}>
            Safety Report
          </span>
        </div>

        {/* Product info + grade */}
        <div style={{
          display: 'flex',
          gap: '20px',
          alignItems: 'flex-start',
        }}>
          {/* Product image */}
          <div style={{
            width: '90px',
            height: '90px',
            borderRadius: '16px',
            overflow: 'hidden',
            background: isDark ? '#2c2c2e' : '#fff',
            boxShadow: '0 2px 12px rgba(0,0,0,0.1)',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            {report.image_url ? (
              <img
                src={report.image_url}
                alt={report.product_name}
                style={{ width: '100%', height: '100%', objectFit: 'contain', padding: '4px' }}
                onError={e => {
                  (e.target as HTMLImageElement).style.display = 'none'
                }}
              />
            ) : (
              <span style={{ fontSize: '36px' }}>
                {report.product_type === 'food' ? '🛒' : '✨'}
              </span>
            )}
          </div>

          {/* Product name + grade */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <span style={{
              fontSize: '11px',
              fontWeight: '600',
              color: secondaryText,
              textTransform: 'uppercase',
              letterSpacing: '0.6px',
            }}>
              {report.product_type === 'food' ? '🍎 Food' : '✨ Cosmetic'}
            </span>
            <h1 style={{
              fontSize: '18px',
              fontWeight: '700',
              color: primaryText,
              lineHeight: 1.3,
              marginTop: '4px',
              marginBottom: '4px',
              overflow: 'hidden',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
            }}>
              {report.product_name || 'Unknown Product'}
            </h1>
            {report.brand && (
              <p style={{ fontSize: '13px', color: secondaryText }}>{report.brand}</p>
            )}
          </div>

          {/* Grade */}
          <GradeCircle grade={report.grade} score={report.score} isDark={isDark} />
        </div>
      </div>

      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Allergen warning banner */}
        {triggeredAllergens.length > 0 && (
          <div style={{
            background: isDark ? 'rgba(255,59,48,0.15)' : '#fff1f0',
            border: '1.5px solid #ff3b30',
            borderRadius: '16px',
            padding: '14px 16px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <span style={{ fontSize: '18px' }}>⚠️</span>
              <p style={{ fontSize: '15px', fontWeight: '700', color: '#ff3b30' }}>
                Allergen Alert
              </p>
            </div>
            <p style={{ fontSize: '13px', color: isDark ? '#ff6b6b' : '#c0392b', marginBottom: '10px', lineHeight: 1.4 }}>
              This product may contain allergens from your profile:
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {triggeredAllergens.map(a => (
                <span key={a.id} style={{
                  background: isDark ? 'rgba(255,59,48,0.2)' : '#ffe5e5',
                  border: '1px solid rgba(255,59,48,0.4)',
                  borderRadius: '20px',
                  padding: '4px 12px',
                  fontSize: '13px',
                  fontWeight: '600',
                  color: '#ff3b30',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                }}>
                  <span>{a.emoji}</span>
                  <span>{a.label}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Recall alert banner */}
        {report.recalls && report.recalls.length > 0 && (
          <div style={{
            background: isDark ? 'rgba(255,59,48,0.18)' : '#fff1f0',
            border: '2px solid #ff3b30',
            borderRadius: '16px',
            padding: '14px 16px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <span style={{ fontSize: '20px' }}>🚨</span>
              <p style={{ fontSize: '15px', fontWeight: '700', color: '#ff3b30' }}>
                Active Recall Alert
              </p>
            </div>
            <p style={{ fontSize: '13px', color: isDark ? '#ff6b6b' : '#c0392b', marginBottom: '10px', lineHeight: 1.4 }}>
              This product may be subject to an EU food safety recall.
              Do not consume and check the official notice.
            </p>
            {report.recalls.map((recall: RecallAlert, i: number) => (
              <div key={i} style={{
                background: isDark ? 'rgba(255,59,48,0.12)' : '#ffe5e5',
                border: '1px solid rgba(255,59,48,0.3)',
                borderRadius: '10px',
                padding: '10px 12px',
                marginBottom: i < report.recalls.length - 1 ? '8px' : 0,
              }}>
                <p style={{ fontSize: '13px', fontWeight: '600', color: isDark ? '#ff6b6b' : '#c0392b', marginBottom: '4px' }}>
                  {recall.title}
                </p>
                {recall.risk_level && (
                  <span style={{
                    display: 'inline-block',
                    background: recall.risk_level === 'serious' || recall.risk_level === 'high'
                      ? '#ff3b30' : '#ff9f0a',
                    color: '#fff',
                    fontSize: '11px',
                    fontWeight: '700',
                    borderRadius: '6px',
                    padding: '2px 8px',
                    textTransform: 'uppercase',
                    marginBottom: '4px',
                  }}>
                    {recall.risk_level} risk
                  </span>
                )}
                {recall.published_at && (
                  <p style={{ fontSize: '11px', color: isDark ? 'rgba(255,107,107,0.7)' : '#e74c3c', marginBottom: recall.link ? '6px' : 0 }}>
                    {new Date(recall.published_at).toLocaleDateString()}
                  </p>
                )}
                {recall.link && (
                  <a
                    href={recall.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: '12px', color: '#ff3b30', fontWeight: '600' }}
                  >
                    View official notice →
                  </a>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Summary card */}
        <div style={{
          background: cardBg,
          borderRadius: '18px',
          padding: '18px',
          boxShadow: cardShadow,
        }}>
          <h2 style={{
            fontSize: '13px',
            fontWeight: '600',
            color: secondaryText,
            textTransform: 'uppercase',
            letterSpacing: '0.6px',
            marginBottom: '10px',
          }}>
            Summary
          </h2>
          <p style={{
            fontSize: '15px',
            color: primaryText,
            lineHeight: 1.7,
          }}>
            {report.summary}
          </p>
        </div>

        {/* Ingredient stats */}
        {report.ingredients_analysis.length > 0 && (
          <div style={{
            background: cardBg,
            borderRadius: '18px',
            padding: '18px',
            boxShadow: cardShadow,
          }}>
            <h2 style={{
              fontSize: '13px',
              fontWeight: '600',
              color: secondaryText,
              textTransform: 'uppercase',
              letterSpacing: '0.6px',
              marginBottom: '14px',
            }}>
              Ingredient Overview
            </h2>
            <div style={{ display: 'flex', gap: '10px' }}>
              {statItems.map(({ count, label, color, bg: statBg }) => (
                <div key={label} style={{
                  flex: 1,
                  background: statBg,
                  borderRadius: '12px',
                  padding: '14px 10px',
                  textAlign: 'center',
                }}>
                  <p style={{
                    fontSize: '26px',
                    fontWeight: '700',
                    color,
                    lineHeight: 1,
                    marginBottom: '4px',
                  }}>
                    {count}
                  </p>
                  <p style={{
                    fontSize: '12px',
                    fontWeight: '600',
                    color,
                    opacity: 0.8,
                  }}>
                    {label}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Positive points */}
        {report.positive_points.length > 0 && (
          <div style={{
            background: cardBg,
            borderRadius: '18px',
            padding: '18px',
            boxShadow: cardShadow,
          }}>
            <h2 style={{
              fontSize: '13px',
              fontWeight: '600',
              color: secondaryText,
              textTransform: 'uppercase',
              letterSpacing: '0.6px',
              marginBottom: '12px',
            }}>
              Positive Points
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {report.positive_points.map((point, i) => (
                <div key={i} style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                }}>
                  <span style={{
                    width: '22px',
                    height: '22px',
                    borderRadius: '50%',
                    background: isDark ? '#0d3320' : '#e8f8ed',
                    color: '#34c759',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '12px',
                    fontWeight: '700',
                    flexShrink: 0,
                    marginTop: '1px',
                  }}>
                    ✓
                  </span>
                  <p style={{
                    fontSize: '14px',
                    color: primaryText,
                    lineHeight: 1.5,
                  }}>
                    {point}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Negative points */}
        {report.negative_points.length > 0 && (
          <div style={{
            background: cardBg,
            borderRadius: '18px',
            padding: '18px',
            boxShadow: cardShadow,
          }}>
            <h2 style={{
              fontSize: '13px',
              fontWeight: '600',
              color: secondaryText,
              textTransform: 'uppercase',
              letterSpacing: '0.6px',
              marginBottom: '12px',
            }}>
              Points of Concern
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {report.negative_points.map((point, i) => (
                <div key={i} style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                }}>
                  <span style={{
                    width: '22px',
                    height: '22px',
                    borderRadius: '50%',
                    background: isDark ? '#330d0a' : '#ffe8e6',
                    color: '#ff3b30',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '12px',
                    fontWeight: '700',
                    flexShrink: 0,
                    marginTop: '1px',
                  }}>
                    ✕
                  </span>
                  <p style={{
                    fontSize: '14px',
                    color: primaryText,
                    lineHeight: 1.5,
                  }}>
                    {point}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Ingredients breakdown */}
        {report.ingredients_analysis.length > 0 && (
          <div style={{
            background: cardBg,
            borderRadius: '18px',
            padding: '18px',
            boxShadow: cardShadow,
          }}>
            <h2 style={{
              fontSize: '13px',
              fontWeight: '600',
              color: secondaryText,
              textTransform: 'uppercase',
              letterSpacing: '0.6px',
              marginBottom: '14px',
            }}>
              Ingredient Breakdown
            </h2>

            {['avoid', 'caution', 'safe'].map(level => {
              const items = report.ingredients_analysis.filter(i => i.safety_level === level)
              if (items.length === 0) return null
              const palette = SAFETY_COLORS[level as keyof typeof SAFETY_COLORS]
              const colors = isDark ? palette.dark : palette.light
              const labels = { avoid: 'Avoid', caution: 'Use with Caution', safe: 'Safe' }

              return (
                <div key={level} style={{ marginBottom: '14px' }}>
                  <p style={{
                    fontSize: '12px',
                    fontWeight: '700',
                    color: colors.text,
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                    marginBottom: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}>
                    <span style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: colors.dot,
                      display: 'inline-block',
                    }} />
                    {labels[level as keyof typeof labels]}
                  </p>
                  {items.map((ingredient, i) => (
                    <IngredientBadge key={i} ingredient={ingredient} isDark={isDark} />
                  ))}
                </div>
              )
            })}
          </div>
        )}

        {/* Barcode info */}
        <div style={{
          background: cardBg,
          borderRadius: '18px',
          padding: '14px 18px',
          boxShadow: cardShadow,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span style={{ fontSize: '13px', color: secondaryText }}>Barcode</span>
          <span style={{
            fontSize: '13px',
            fontWeight: '600',
            color: primaryText,
            fontFamily: 'monospace',
          }}>
            {report.barcode}
          </span>
        </div>
      </div>

      {/* Fixed bottom button */}
      <div style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        padding: '16px 20px 28px',
        background: bottomGradient,
      }}>
        <button
          onClick={onScanAgain}
          style={{
            width: '100%',
            padding: '16px',
            borderRadius: '16px',
            border: 'none',
            background: scanBtnBg,
            color: scanBtnText,
            fontSize: '16px',
            fontWeight: '600',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
          }}
        >
          <span>🔍</span>
          <span>Scan Another Product</span>
        </button>
      </div>
    </div>
  )
}
