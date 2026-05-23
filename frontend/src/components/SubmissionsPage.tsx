import { useState, useEffect, useCallback } from 'react'
import { getSubmissions } from '../api'
import type { UserSubmission, SafetyReport } from '../types'
import { getTheme, glassStyle, FONT_STACK } from '../theme'

interface SubmissionsPageProps {
  onBack:      () => void
  onViewReport: (report: SafetyReport) => void
  isDark?:     boolean
}

const STATUS_CONFIG = {
  pending:   { label: 'Pending',   color: '#71717a', bg: 'rgba(113,113,122,0.15)', emoji: '⏳' },
  analyzing: { label: 'Analyzing', color: '#f59e0b', bg: 'rgba(245,158,11,0.15)',  emoji: '🔄' },
  complete:  { label: 'Complete',  color: '#22c55e', bg: 'rgba(34,197,94,0.15)',   emoji: '✅' },
  failed:    { label: 'Failed',    color: '#ef4444', bg: 'rgba(239,68,68,0.15)',   emoji: '❌' },
}

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins  = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days  = Math.floor(diff / 86400000)
  if (mins < 1)   return 'just now'
  if (mins < 60)  return `${mins}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${days}d ago`
}

const GRADE_COLOR: Record<string, string> = {
  A: '#22c55e', B: '#84cc16', C: '#f59e0b', D: '#ef4444'
}

export default function SubmissionsPage({ onBack, onViewReport, isDark = false }: SubmissionsPageProps) {
  const [submissions, setSubmissions] = useState<UserSubmission[]>([])
  const [loading,     setLoading]     = useState(true)

  const theme     = getTheme(isDark)
  const primary   = theme.primary
  const secondary = theme.tertiary
  const border    = theme.glassBorder
  const backBg    = theme.ingredientBg
  const headerStyle: React.CSSProperties = {
    ...glassStyle(theme),
    borderRadius: 0,
    borderLeft: 'none',
    borderRight: 'none',
    borderTop: 'none',
    boxShadow: 'none',
  }
  const rootStyle: React.CSSProperties = {
    minHeight: '100vh',
    background: theme.bg,
    backgroundImage: theme.bgGradient,
    color: theme.primary,
    fontFamily: FONT_STACK,
  }

  const load = useCallback(async () => {
    try {
      const data = await getSubmissions()
      setSubmissions(data)
    } catch {
      // non-fatal
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Auto-refresh every 4s while any submission is still analyzing
  useEffect(() => {
    const hasActive = submissions.some(s => s.status === 'analyzing' || s.status === 'pending')
    if (!hasActive) return
    const timer = setInterval(load, 4000)
    return () => clearInterval(timer)
  }, [submissions, load])

  return (
    <div style={rootStyle}>
      {/* Header */}
      <div style={{
        ...headerStyle,
        padding: '20px 20px 16px', position: 'sticky', top: 0, zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button onClick={onBack} style={{
            background: backBg, border: 'none', borderRadius: '50%',
            width: '36px', height: '36px', cursor: 'pointer', fontSize: '16px', color: primary,
          }}>←</button>
          <span style={{ flex: 1, textAlign: 'center', fontSize: '17px', fontWeight: '700', color: primary }}>
            My Submissions
          </span>
          <button onClick={load} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: '18px', padding: '4px',
          }}>↻</button>
        </div>
      </div>

      <div className="fade-up stagger-1" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {loading && (
          <p style={{ textAlign: 'center', color: secondary, fontSize: '14px', padding: '40px 0' }}>
            Loading...
          </p>
        )}

        {!loading && submissions.length === 0 && (
          <div style={{
            textAlign: 'center', padding: '60px 20px',
            color: secondary, fontSize: '15px', lineHeight: 1.6,
          }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>📦</div>
            <p>No submissions yet.</p>
            <p style={{ fontSize: '13px', marginTop: '8px' }}>
              Use the + button in the scanner to add a product manually.
            </p>
          </div>
        )}

        {submissions.map(sub => {
          const cfg   = STATUS_CONFIG[sub.status] ?? STATUS_CONFIG.pending
          const name  = sub.product_name || 'Unknown product'
          const brand = sub.brand || ''
          const report = sub.report

          return (
            <div
              key={sub.id}
              onClick={() => report && onViewReport(report as SafetyReport)}
              className={report ? 'lift press' : ''}
              style={{
                ...glassStyle(theme),
                borderRadius: '16px',
                padding: '16px',
                boxShadow: theme.glassShadow,
                cursor: report ? 'pointer' : 'default',
                border: `1px solid ${report ? `${theme.accent}66` : border}`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                {/* Grade badge (if complete) */}
                <div style={{
                  width: '44px', height: '44px', borderRadius: '12px', flexShrink: 0,
                  background: report
                    ? theme.greenSoft
                    : theme.ingredientBg,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: report ? '20px' : '22px',
                  fontWeight: '800',
                  color: report ? GRADE_COLOR[(report as SafetyReport).grade] : secondary,
                }}>
                  {report ? (report as SafetyReport).grade : '?'}
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontSize: '15px', fontWeight: '600', color: primary, marginBottom: '2px' }}>
                    {name}
                  </p>
                  {brand && (
                    <p style={{ fontSize: '13px', color: secondary, marginBottom: '4px' }}>{brand}</p>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    {/* Status badge */}
                    <span style={{
                      fontSize: '11px', fontWeight: '600',
                      color: cfg.color, background: cfg.bg,
                      borderRadius: '6px', padding: '2px 8px',
                      display: 'flex', alignItems: 'center', gap: '4px',
                    }}>
                      <span>{cfg.emoji}</span>
                      <span>{cfg.label}</span>
                    </span>
                    {sub.barcode && (
                      <span style={{ fontSize: '11px', color: secondary, fontFamily: 'monospace' }}>
                        {sub.barcode}
                      </span>
                    )}
                    <span style={{ fontSize: '11px', color: secondary }}>
                      {timeAgo(sub.submitted_at)}
                    </span>
                  </div>

                  {/* Analyzing pulse */}
                  {sub.status === 'analyzing' && (
                    <p style={{ fontSize: '12px', color: '#f59e0b', marginTop: '6px' }}>
                      Analysis in progress — check back in a moment
                    </p>
                  )}

                  {/* Error */}
                  {sub.status === 'failed' && sub.error && (
                    <p style={{ fontSize: '12px', color: theme.red, marginTop: '6px' }}>
                      {sub.error.slice(0, 80)}
                    </p>
                  )}

                  {/* Tap hint */}
                  {sub.status === 'complete' && report && (
                    <p style={{ fontSize: '12px', color: theme.green, marginTop: '6px' }}>
                      Tap to view safety report →
                    </p>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
