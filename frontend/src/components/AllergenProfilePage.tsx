import { ALL_ALLERGENS } from '../hooks/useAllergenProfile'

interface AllergenProfilePageProps {
  activeIds:      string[]
  onToggle:       (id: string) => void
  onClear:        () => void
  onBack:         () => void
  isDark?:        boolean
}

export default function AllergenProfilePage({
  activeIds, onToggle, onClear, onBack, isDark = false,
}: AllergenProfilePageProps) {
  const bg       = isDark ? '#000'    : '#f5f5f7'
  const headerBg = isDark ? '#1c1c1e' : '#fff'
  const primary  = isDark ? '#f2f2f7' : '#1c1c1e'
  const secondary = '#8e8e93'
  const border   = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'
  const backBg   = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'
  const cardOff  = isDark ? 'rgba(255,255,255,0.04)' : '#fff'
  const cardOffBorder = isDark ? 'rgba(255,255,255,0.08)' : '#e5e5ea'

  return (
    <div style={{ minHeight: '100vh', background: bg }}>
      {/* Header */}
      <div style={{
        background: headerBg,
        borderBottom: `1px solid ${border}`,
        padding: '20px 20px 16px',
        position: 'sticky', top: 0, zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button onClick={onBack} style={{
            background: backBg, border: 'none', borderRadius: '50%',
            width: '36px', height: '36px', cursor: 'pointer',
            fontSize: '16px', color: primary, flexShrink: 0,
          }}>←</button>

          <span style={{
            flex: 1, textAlign: 'center',
            fontSize: '17px', fontWeight: '700', color: primary,
          }}>
            Allergen Profile
          </span>

          {activeIds.length > 0 && (
            <button onClick={onClear} style={{
              background: 'none', border: 'none',
              fontSize: '14px', fontWeight: '500',
              color: '#ff3b30', cursor: 'pointer', padding: '4px 0',
            }}>
              Clear
            </button>
          )}
        </div>
      </div>

      <div style={{ padding: '20px' }}>
        {/* Description */}
        <div style={{
          background: isDark ? 'rgba(52,199,89,0.08)' : '#e8f8ed',
          border: `1px solid ${isDark ? 'rgba(52,199,89,0.2)' : 'rgba(52,199,89,0.3)'}`,
          borderRadius: '14px',
          padding: '14px 16px',
          marginBottom: '20px',
        }}>
          <p style={{ fontSize: '14px', color: isDark ? '#4cd964' : '#1a7a35', lineHeight: 1.5 }}>
            Select the allergens you want to watch for. Any product containing these ingredients will show a warning on its safety report.
          </p>
        </div>

        {activeIds.length > 0 && (
          <p style={{ fontSize: '13px', color: secondary, marginBottom: '14px' }}>
            {activeIds.length} allergen{activeIds.length !== 1 ? 's' : ''} active
          </p>
        )}

        {/* Grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '10px',
        }}>
          {ALL_ALLERGENS.map(allergen => {
            const active = activeIds.includes(allergen.id)
            return (
              <button
                key={allergen.id}
                onClick={() => onToggle(allergen.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '14px',
                  borderRadius: '14px',
                  border: active
                    ? '2px solid #34c759'
                    : `2px solid ${cardOffBorder}`,
                  background: active
                    ? (isDark ? 'rgba(52,199,89,0.12)' : '#e8f8ed')
                    : cardOff,
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                }}
              >
                <span style={{ fontSize: '26px', flexShrink: 0 }}>{allergen.emoji}</span>
                <div style={{ minWidth: 0 }}>
                  <p style={{
                    fontSize: '14px',
                    fontWeight: '600',
                    color: active ? '#34c759' : primary,
                    whiteSpace: 'nowrap',
                  }}>
                    {allergen.label}
                  </p>
                  {active && (
                    <p style={{ fontSize: '11px', color: '#34c759', opacity: 0.8 }}>Active</p>
                  )}
                </div>
                {/* Checkmark */}
                <div style={{
                  marginLeft: 'auto',
                  width: '20px',
                  height: '20px',
                  borderRadius: '50%',
                  background: active ? '#34c759' : 'transparent',
                  border: active ? 'none' : `2px solid ${isDark ? 'rgba(255,255,255,0.2)' : '#d1d1d6'}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  fontSize: '11px',
                  color: '#fff',
                  fontWeight: '700',
                }}>
                  {active && '✓'}
                </div>
              </button>
            )
          })}
        </div>

        <p style={{
          fontSize: '12px',
          color: secondary,
          textAlign: 'center',
          marginTop: '24px',
          lineHeight: 1.6,
        }}>
          Based on the EU 14 major allergens.<br />
          Matching is keyword-based and may not catch all cases.
        </p>
      </div>
    </div>
  )
}
