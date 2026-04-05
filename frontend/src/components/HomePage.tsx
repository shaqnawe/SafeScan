import type { ScanHistoryEntry } from '../hooks/useScanHistory'

interface HomePageProps {
  onStartScanning:  () => void
  onViewHistory:    () => void
  onAllergenProfile: () => void
  history:          ScanHistoryEntry[]
  activeAllergenCount: number
}

const FEATURES = [
  {
    emoji: '🧬',
    title: 'Ingredient Analysis',
    desc: '2M+ products cross-referenced against EU safety regulations',
  },
  {
    emoji: '🍎',
    title: 'Food Safety',
    desc: 'Nutri-Score, NOVA processing level, additives and allergens',
  },
  {
    emoji: '✨',
    title: 'Cosmetic Safety',
    desc: 'Parabens, endocrine disruptors, banned EU substances',
  },
]

export default function HomePage({ onStartScanning, onViewHistory, onAllergenProfile, history, activeAllergenCount }: HomePageProps) {
  return (
    <div style={{
      minHeight: '100vh',
      background: '#000',
      display: 'flex',
      flexDirection: 'column',
      color: '#fff',
      overflowX: 'hidden',
    }}>
      {/* Background glow */}
      <div style={{
        position: 'fixed',
        top: '-120px',
        left: '50%',
        transform: 'translateX(-50%)',
        width: '500px',
        height: '500px',
        background: 'radial-gradient(circle, rgba(52,199,89,0.12) 0%, transparent 70%)',
        pointerEvents: 'none',
        zIndex: 0,
      }} />

      {/* Top-right buttons */}
      <div style={{
        position: 'fixed',
        top: '20px',
        right: '20px',
        zIndex: 10,
        display: 'flex',
        gap: '8px',
      }}>
        {/* Allergen profile button */}
        <button
          onClick={onAllergenProfile}
          style={{
            background: activeAllergenCount > 0 ? 'rgba(52,199,89,0.15)' : 'rgba(255,255,255,0.08)',
            border: activeAllergenCount > 0 ? '1px solid rgba(52,199,89,0.4)' : '1px solid rgba(255,255,255,0.1)',
            borderRadius: '20px',
            padding: '8px 14px',
            color: activeAllergenCount > 0 ? '#34c759' : 'rgba(255,255,255,0.7)',
            fontSize: '13px',
            fontWeight: '500',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span>🌾</span>
          <span>{activeAllergenCount > 0 ? `${activeAllergenCount} allergen${activeAllergenCount !== 1 ? 's' : ''}` : 'Allergens'}</span>
        </button>

        {/* History button */}
        {history.length > 0 && (
          <button
            onClick={onViewHistory}
            style={{
              background: 'rgba(255,255,255,0.08)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '20px',
              padding: '8px 14px',
              color: 'rgba(255,255,255,0.7)',
              fontSize: '13px',
              fontWeight: '500',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>🕐</span>
            <span>{history.length} scan{history.length !== 1 ? 's' : ''}</span>
          </button>
        )}
      </div>

      {/* Hero */}
      <div style={{
        position: 'relative',
        zIndex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        padding: '80px 32px 48px',
      }}>
        {/* Icon */}
        <div style={{
          width: '88px',
          height: '88px',
          borderRadius: '24px',
          background: 'linear-gradient(135deg, #1a3d24 0%, #0d2016 100%)',
          border: '1px solid rgba(52,199,89,0.3)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '42px',
          marginBottom: '24px',
          boxShadow: '0 0 40px rgba(52,199,89,0.15)',
        }}>
          🔍
        </div>

        {/* Name */}
        <h1 style={{
          fontSize: '42px',
          fontWeight: '800',
          letterSpacing: '-1px',
          marginBottom: '12px',
          background: 'linear-gradient(135deg, #fff 40%, #34c759 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
        }}>
          SafeScan
        </h1>

        {/* Tagline */}
        <p style={{
          fontSize: '18px',
          color: 'rgba(255,255,255,0.6)',
          lineHeight: 1.5,
          maxWidth: '280px',
          marginBottom: '40px',
        }}>
          Scan any product. Know exactly what's inside.
        </p>

        {/* CTA */}
        <button
          onClick={onStartScanning}
          style={{
            padding: '18px 48px',
            borderRadius: '18px',
            border: 'none',
            background: '#34c759',
            color: '#fff',
            fontSize: '18px',
            fontWeight: '700',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            boxShadow: '0 4px 24px rgba(52,199,89,0.35)',
            letterSpacing: '-0.2px',
          }}
        >
          <span style={{ fontSize: '20px' }}>📷</span>
          <span>Start Scanning</span>
        </button>

        <p style={{
          marginTop: '16px',
          fontSize: '13px',
          color: 'rgba(255,255,255,0.3)',
        }}>
          Point at a barcode — results in seconds
        </p>
      </div>

      {/* Feature cards */}
      <div style={{
        position: 'relative',
        zIndex: 1,
        padding: '0 20px 48px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}>
        {FEATURES.map(f => (
          <div key={f.title} style={{
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: '16px',
            padding: '18px 20px',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
          }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'rgba(52,199,89,0.1)',
              border: '1px solid rgba(52,199,89,0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '22px',
              flexShrink: 0,
            }}>
              {f.emoji}
            </div>
            <div>
              <p style={{
                fontSize: '15px',
                fontWeight: '600',
                color: '#fff',
                marginBottom: '3px',
              }}>
                {f.title}
              </p>
              <p style={{
                fontSize: '13px',
                color: 'rgba(255,255,255,0.45)',
                lineHeight: 1.4,
              }}>
                {f.desc}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div style={{
        position: 'relative',
        zIndex: 1,
        textAlign: 'center',
        padding: '0 20px 40px',
      }}>
        <p style={{
          fontSize: '12px',
          color: 'rgba(255,255,255,0.2)',
          lineHeight: 1.6,
        }}>
          Powered by Claude AI · EU ingredient database · Open Food Facts
        </p>
      </div>
    </div>
  )
}
