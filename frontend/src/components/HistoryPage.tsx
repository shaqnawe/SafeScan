import type { ScanHistoryEntry } from '../hooks/useScanHistory'

interface HistoryPageProps {
  history: ScanHistoryEntry[]
  onBack: () => void
  onRescan: (barcode: string) => void
  onClear: () => void
  isDark?: boolean
}

const GRADE_COLOR: Record<string, string> = {
  A: '#34c759', B: '#a3d977', C: '#ff9f0a', D: '#ff3b30', E: '#9c2b2b',
}

const GRADE_BG_LIGHT: Record<string, string> = {
  A: '#e8f8ed', B: '#f0f7e6', C: '#fff4e0', D: '#ffe8e6', E: '#f5e0e0',
}

const GRADE_BG_DARK: Record<string, string> = {
  A: '#0d3320', B: '#1e3310', C: '#332500', D: '#330d0a', E: '#2e1515',
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
  const bg        = isDark ? '#000'     : '#f5f5f7'
  const cardBg    = isDark ? '#1c1c1e'  : '#fff'
  const headerBg  = isDark ? '#1c1c1e'  : '#fff'
  const primary   = isDark ? '#f2f2f7'  : '#1c1c1e'
  const secondary = '#8e8e93'
  const border    = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'
  const shadow    = isDark ? '0 1px 6px rgba(0,0,0,0.4)' : '0 1px 6px rgba(0,0,0,0.05)'
  const backBg    = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'

  return (
    <div style={{ minHeight: '100vh', background: bg }}>
      {/* Header */}
      <div style={{
        background: headerBg,
        borderBottom: `1px solid ${border}`,
        padding: '20px 20px 16px',
        position: 'sticky',
        top: 0,
        zIndex: 10,
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
                fontWeight: '500',
                color: '#ff3b30',
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
              background: '#34c759',
              color: '#fff',
              fontSize: '15px',
              fontWeight: '600',
              cursor: 'pointer',
            }}
          >
            Start Scanning
          </button>
        </div>
      )}

      {/* List */}
      {history.length > 0 && (
        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
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
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '14px',
                  background: cardBg,
                  borderRadius: '16px',
                  padding: '14px',
                  border: 'none',
                  cursor: 'pointer',
                  boxShadow: shadow,
                  textAlign: 'left',
                  width: '100%',
                }}
              >
                {/* Thumbnail */}
                <div style={{
                  width: '56px',
                  height: '56px',
                  borderRadius: '12px',
                  background: isDark ? '#2c2c2e' : '#f5f5f7',
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
