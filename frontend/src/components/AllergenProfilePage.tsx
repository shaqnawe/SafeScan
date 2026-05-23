import { ALL_ALLERGENS } from '../hooks/useAllergenProfile'
import { getTheme, glassStyle, FONT_STACK } from '../theme'

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
  const theme = getTheme(isDark)
  const primary  = theme.primary
  const secondary = theme.tertiary
  const backBg   = theme.ingredientBg
  void backBg // keep for the back button

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
        boxShadow: 'none',
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
              fontSize: '14px', fontWeight: '600',
              color: theme.red, cursor: 'pointer', padding: '4px 0',
            }}>
              Clear
            </button>
          )}
        </div>
      </div>

      <div style={{ padding: '20px' }}>
        {/* Description */}
        <div style={{
          ...glassStyle(theme),
          background: theme.accentSoft,
          border: `1px solid ${theme.accent}40`,
          padding: '14px 16px',
          marginBottom: '20px',
        }}>
          <p style={{ fontSize: '14px', color: theme.accent, lineHeight: 1.5, fontWeight: 500 }}>
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
                  ...glassStyle(theme),
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '14px',
                  borderRadius: 16,
                  border: active
                    ? `2px solid ${theme.accent}`
                    : `1px solid ${theme.glassBorder}`,
                  background: active ? theme.accentSoft : theme.glass,
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                  fontFamily: FONT_STACK,
                  boxShadow: active ? `0 4px 16px ${theme.accent}33` : theme.glassShadow,
                }}
              >
                <span style={{ fontSize: '26px', flexShrink: 0 }}>{allergen.emoji}</span>
                <div style={{ minWidth: 0 }}>
                  <p style={{
                    fontSize: '14px',
                    fontWeight: '700',
                    color: active ? theme.accent : primary,
                    whiteSpace: 'nowrap',
                  }}>
                    {allergen.label}
                  </p>
                  {active && (
                    <p style={{ fontSize: '11px', color: theme.accent, opacity: 0.9, marginTop: 2 }}>Active</p>
                  )}
                </div>
                {/* Checkmark */}
                <div style={{
                  marginLeft: 'auto',
                  width: '20px',
                  height: '20px',
                  borderRadius: '50%',
                  background: active ? theme.accent : 'transparent',
                  border: active ? 'none' : `2px solid ${theme.glassBorder}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  fontSize: '11px',
                  color: theme.btnText,
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
