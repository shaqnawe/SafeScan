import type { ScanHistoryEntry } from '../hooks/useScanHistory'
import { getTheme, glassStyle, FONT_STACK } from '../theme'

interface HistoryPageProps {
  history: ScanHistoryEntry[]
  onBack: () => void
  onRescan: (barcode: string) => void
  onClear: () => void
  isDark?: boolean
}

const GRADE_COLOR: Record<string, string> = {
  A: '#22c55e', B: '#84cc16', C: '#f59e0b', D: '#ef4444'
}

const GRADE_BG_LIGHT: Record<string, string> = {
  A: 'rgba(34,197,94,0.12)',  B: 'rgba(132,204,22,0.12)',
  C: 'rgba(245,158,11,0.12)', D: 'rgba(239,68,68,0.12)',
}

const GRADE_BG_DARK: Record<string, string> = {
  A: 'rgba(34,197,94,0.15)',  B: 'rgba(132,204,22,0.15)',
  C: 'rgba(245,158,11,0.15)', D: 'rgba(239,68,68,0.15)',
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1)  return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)  return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export default function HistoryPage({ history, onBack, onRescan, onClear, isDark = false }: HistoryPageProps) {
  const theme = getTheme(isDark)
  const primary   = theme.primary
  const secondary = theme.tertiary
  const backBg    = theme.ingredientBg

  return (
    <div style={{
      minHeight: '100vh',
      background: theme.bg,
      backgroundImage: theme.bgGradient,
      color: theme.primary,
      fontFamily: FONT_STACK,
    }}>
      {/* Header */}
      <div style={{
        ...glassStyle(theme),
        borderRadius: 0,
        borderLeft: 'none',
        borderRight: 'none',
        borderTop: 'none',
        padding: '20px 20px 16px',
        position: 'sticky',
        top: 0,
        zIndex: 10,
        boxShadow: 'none',
      }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button
            onClick={onBack}
            style={{
              background: backBg,
              border: 'none',
              borderRadius: '50%',
              width: '36px',
              height: '36px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              fontSize: '16px',
              color: primary,
              flexShrink: 0,
            }}
          >
            ←
          </button>

          <span style={{
            flex: 1,
            textAlign: 'center',
            fontSize: '17px',
            fontWeight: '700',
            color: primary,
          }}>
            Scan History
          </span>

          {history.length > 0 && (
            <button
              onClick={onClear}
              style={{
                background: 'none',
                border: 'none',
                fontSize: '14px',
                fontWeight: '600',
                color: theme.red,
                cursor: 'pointer',
                padding: '4px 0',
              }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Empty state */}
      {history.length === 0 && (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: 'calc(100vh - 80px)',
          gap: '12px',
          padding: '40px',
        }}>
          <span style={{ fontSize: '56px' }}>🔍</span>
          <p style={{ fontSize: '18px', fontWeight: '600', color: primary }}>No scans yet</p>
          <p style={{ fontSize: '14px', color: secondary, textAlign: 'center' }}>
            Products you scan will appear here
          </p>
          <button
            onClick={onBack}
            style={{
              marginTop: '8px',
              padding: '14px 32px',
              borderRadius: '14px',
              border: 'none',
              background: theme.gradeGradient,
              color: theme.btnText,
              fontSize: '15px',
              fontWeight: '700',
              cursor: 'pointer',
              boxShadow: theme.ctaShadow,
              fontFamily: FONT_STACK,
            }}
          >
            Start Scanning
          </button>
        </div>
      )}

      {/* List */}
      {history.length > 0 && (
        <div className="fade-up stagger-1" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <p style={{ fontSize: '13px', color: secondary, marginBottom: '4px' }}>
            {history.length} product{history.length !== 1 ? 's' : ''} scanned
          </p>

          {history.map(entry => {
            const gradeColor = GRADE_COLOR[entry.grade] || '#8e8e93'
            const gradeBg = isDark
              ? (GRADE_BG_DARK[entry.grade] || '#2c2c2e')
              : (GRADE_BG_LIGHT[entry.grade] || '#f5f5f7')

            return (
              <button
                key={entry.barcode + entry.scanned_at}
                onClick={() => onRescan(entry.barcode)}
                className="lift press"
                style={{
                  ...glassStyle(theme),
                  display: 'flex',
                  alignItems: 'center',
                  gap: '14px',
                  borderRadius: 18,
                  padding: '14px',
                  cursor: 'pointer',
                  textAlign: 'left',
                  width: '100%',
                  color: theme.primary,
                  fontFamily: FONT_STACK,
                }}
              >
                {/* Thumbnail */}
                <div style={{
                  width: '56px',
                  height: '56px',
                  borderRadius: '12px',
                  background: theme.ingredientBg,
                  border: `1px solid ${theme.glassBorder}`,
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                }}>
                  {entry.image_url ? (
                    <img
                      src={entry.image_url}
                      alt={entry.name}
                      style={{ width: '100%', height: '100%', objectFit: 'contain', padding: '4px' }}
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  ) : (
                    <span style={{ fontSize: '26px' }}>
                      {entry.product_type === 'food' ? '🛒' : '✨'}
                    </span>
                  )}
                </div>

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{
                    fontSize: '15px',
                    fontWeight: '600',
                    color: primary,
                    marginBottom: '2px',
                    overflow: 'hidden',
                    whiteSpace: 'nowrap',
                    textOverflow: 'ellipsis',
                  }}>
                    {entry.name}
                  </p>
                  {entry.brand && (
                    <p style={{ fontSize: '13px', color: secondary, marginBottom: '4px' }}>
                      {entry.brand}
                    </p>
                  )}
                  <p style={{ fontSize: '12px', color: secondary }}>
                    {timeAgo(entry.scanned_at)}
                  </p>
                </div>

                {/* Grade */}
                <div style={{
                  background: gradeBg,
                  borderRadius: '12px',
                  padding: '8px 12px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  flexShrink: 0,
                }}>
                  <span style={{
                    fontSize: '22px',
                    fontWeight: '800',
                    color: gradeColor,
                    lineHeight: 1,
                  }}>
                    {entry.grade}
                  </span>
                  <span style={{
                    fontSize: '11px',
                    color: gradeColor,
                    fontWeight: '600',
                    opacity: 0.8,
                  }}>
                    {entry.score}
                  </span>
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
