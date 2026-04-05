import { useState } from 'react'
import { scanBarcode } from '../api'
import type { SafetyReport } from '../types'

interface ComparisonPageProps {
  onBack:  () => void
  isDark?: boolean
}

const GRADE_COLOR: Record<string, string> = {
  A: '#34c759', B: '#a3d977', C: '#ff9f0a', D: '#ff3b30', E: '#9c2b2b',
}

type SlotState = 'empty' | 'loading' | 'done' | 'error'

interface Slot {
  state:   SlotState
  barcode: string
  report:  SafetyReport | null
  error:   string
}

const EMPTY_SLOT: Slot = { state: 'empty', barcode: '', report: null, error: '' }


export default function ComparisonPage({ onBack, isDark = false }: ComparisonPageProps) {
  const [slotA, setSlotA] = useState<Slot>(EMPTY_SLOT)
  const [slotB, setSlotB] = useState<Slot>(EMPTY_SLOT)

  const bg       = isDark ? '#000'    : '#f5f5f7'
  const headerBg = isDark ? '#1c1c1e' : '#fff'
  const cardBg   = isDark ? '#1c1c1e' : '#fff'
  const primary  = isDark ? '#f2f2f7' : '#1c1c1e'
  const secondary = '#8e8e93'
  const border   = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'
  const shadow   = isDark ? '0 1px 8px rgba(0,0,0,0.4)' : '0 1px 8px rgba(0,0,0,0.06)'
  const inputBg  = isDark ? '#2c2c2e' : '#f5f5f7'
  const inputBorder = isDark ? 'rgba(255,255,255,0.1)' : '#e5e5ea'
  const backBg   = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'
  const rowBg    = isDark ? 'rgba(255,255,255,0.04)' : '#f9f9fb'
  const winBg    = isDark ? 'rgba(52,199,89,0.12)' : '#e8f8ed'

  async function analyze(which: 'a' | 'b') {
    const slot = which === 'a' ? slotA : slotB
    const set  = which === 'a' ? setSlotA : setSlotB
    if (!slot.barcode.trim()) return
    set(s => ({ ...s, state: 'loading', error: '' }))
    try {
      const report = await scanBarcode(slot.barcode.trim())
      set(s => ({ ...s, state: 'done', report }))
    } catch (err) {
      set(s => ({ ...s, state: 'error', error: err instanceof Error ? err.message : 'Failed' }))
    }
  }

  const bothDone = slotA.state === 'done' && slotB.state === 'done'
  const rA = slotA.report
  const rB = slotB.report

  // Derived comparison stats
  const safeA    = rA ? rA.ingredients_analysis.filter(i => i.safety_level === 'safe').length    : 0
  const cautionA = rA ? rA.ingredients_analysis.filter(i => i.safety_level === 'caution').length : 0
  const avoidA   = rA ? rA.ingredients_analysis.filter(i => i.safety_level === 'avoid').length   : 0
  const safeB    = rB ? rB.ingredients_analysis.filter(i => i.safety_level === 'safe').length    : 0
  const cautionB = rB ? rB.ingredients_analysis.filter(i => i.safety_level === 'caution').length : 0
  const avoidB   = rB ? rB.ingredients_analysis.filter(i => i.safety_level === 'avoid').length   : 0

  // Overall winner: higher score wins; tie-break on fewer avoids
  let winner: 'a' | 'b' | 'tie' = 'tie'
  if (bothDone && rA && rB) {
    if (rA.score !== rB.score)      winner = rA.score > rB.score ? 'a' : 'b'
    else if (avoidA !== avoidB)     winner = avoidA < avoidB ? 'a' : 'b'
    else if (safeA !== safeB)       winner = safeA > safeB ? 'a' : 'b'
  }

  // ── Input slot ──────────────────────────────────────────────────────────
  function SlotInput({ which }: { which: 'a' | 'b' }) {
    const slot   = which === 'a' ? slotA : slotB
    const set    = which === 'a' ? setSlotA : setSlotB
    const label  = which === 'a' ? 'Product A' : 'Product B'
    const isWinner = bothDone && winner === which

    return (
      <div style={{
        flex: 1,
        background: cardBg,
        borderRadius: '16px',
        padding: '14px',
        boxShadow: shadow,
        border: isWinner ? '2px solid #34c759' : `1px solid ${border}`,
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}>
        {/* Grade circle */}
        <div style={{ textAlign: 'center' }}>
          {slot.report ? (
            <>
              <div style={{
                width: '56px', height: '56px', borderRadius: '50%',
                background: GRADE_COLOR[slot.report.grade] + '22',
                border: `3px solid ${GRADE_COLOR[slot.report.grade]}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 6px',
                fontSize: '22px', fontWeight: '800',
                color: GRADE_COLOR[slot.report.grade],
              }}>
                {slot.report.grade}
              </div>
              <p style={{ fontSize: '11px', fontWeight: '700', color: GRADE_COLOR[slot.report.grade] }}>
                {slot.report.score}/100
              </p>
            </>
          ) : (
            <div style={{
              width: '56px', height: '56px', borderRadius: '50%',
              background: inputBg,
              border: `2px dashed ${inputBorder}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 6px',
              fontSize: '20px', color: secondary,
            }}>?</div>
          )}
          {isWinner && (
            <span style={{ fontSize: '11px', color: '#34c759', fontWeight: '700' }}>
              ★ Better choice
            </span>
          )}
        </div>

        {/* Name */}
        {slot.report ? (
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '13px', fontWeight: '600', color: primary, lineHeight: 1.3 }}>
              {slot.report.product_name}
            </p>
            {slot.report.brand && (
              <p style={{ fontSize: '11px', color: secondary }}>{slot.report.brand}</p>
            )}
          </div>
        ) : (
          <p style={{ fontSize: '12px', color: secondary, textAlign: 'center' }}>{label}</p>
        )}

        {/* Input */}
        <div style={{ display: 'flex', gap: '6px' }}>
          <input
            type="text"
            inputMode="numeric"
            placeholder="Barcode"
            value={slot.barcode}
            onChange={e => set(s => ({ ...s, barcode: e.target.value }))}
            onKeyDown={e => e.key === 'Enter' && analyze(which)}
            style={{
              flex: 1, padding: '8px 10px', borderRadius: '10px',
              border: `1px solid ${inputBorder}`, background: inputBg,
              color: primary, fontSize: '13px', outline: 'none',
              minWidth: 0,
            }}
          />
          <button
            onClick={() => analyze(which)}
            disabled={slot.state === 'loading' || !slot.barcode.trim()}
            style={{
              padding: '8px 12px', borderRadius: '10px', border: 'none',
              background: slot.barcode.trim() ? '#34c759' : (isDark ? '#2c2c2e' : '#e5e5ea'),
              color: slot.barcode.trim() ? '#fff' : secondary,
              fontSize: '13px', fontWeight: '600',
              cursor: slot.barcode.trim() ? 'pointer' : 'not-allowed',
              whiteSpace: 'nowrap',
            }}
          >
            {slot.state === 'loading' ? '...' : 'Go'}
          </button>
        </div>

        {slot.state === 'error' && (
          <p style={{ fontSize: '11px', color: '#ff3b30', textAlign: 'center' }}>{slot.error}</p>
        )}
      </div>
    )
  }

  // ── Comparison row ───────────────────────────────────────────────────────
  function CompareRow({
    label, valA, valB, higher = 'better', unit = '',
  }: {
    label: string
    valA: number | string
    valB: number | string
    higher?: 'better' | 'worse' | 'neutral'
    unit?: string
  }) {
    const numA = typeof valA === 'number' ? valA : parseFloat(valA as string)
    const numB = typeof valB === 'number' ? valB : parseFloat(valB as string)
    let rowWin: 'a' | 'b' | 'tie' = 'tie'
    if (!isNaN(numA) && !isNaN(numB) && numA !== numB && higher !== 'neutral') {
      rowWin = higher === 'better'
        ? (numA > numB ? 'a' : 'b')
        : (numA < numB ? 'a' : 'b')
    }

    const cellStyle = (side: 'a' | 'b') => ({
      flex: 1,
      textAlign: 'center' as const,
      padding: '10px 6px',
      borderRadius: '10px',
      background: rowWin === side ? winBg : 'transparent',
      fontWeight: rowWin === side ? '700' : '500',
      color: rowWin === side ? '#34c759' : primary,
      fontSize: '14px',
    })

    return (
      <div style={{
        display: 'flex', alignItems: 'center', gap: '8px',
        background: rowBg, borderRadius: '12px', padding: '2px 8px',
      }}>
        <div style={cellStyle('a')}>{valA}{unit}</div>
        <p style={{ width: '90px', textAlign: 'center', fontSize: '11px', color: secondary, fontWeight: '600', flexShrink: 0 }}>
          {label}
        </p>
        <div style={cellStyle('b')}>{valB}{unit}</div>
      </div>
    )
  }

  const GRADE_RANK: Record<string, number> = { A: 5, B: 4, C: 3, D: 2, E: 1 }

  return (
    <div style={{ minHeight: '100vh', background: bg }}>
      {/* Header */}
      <div style={{
        background: headerBg, borderBottom: `1px solid ${border}`,
        padding: '20px 20px 16px', position: 'sticky', top: 0, zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button onClick={onBack} style={{
            background: backBg, border: 'none', borderRadius: '50%',
            width: '36px', height: '36px', cursor: 'pointer', fontSize: '16px', color: primary,
          }}>←</button>
          <span style={{ flex: 1, textAlign: 'center', fontSize: '17px', fontWeight: '700', color: primary }}>
            Compare Products
          </span>
        </div>
      </div>

      <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {/* Two slots */}
        <div style={{ display: 'flex', gap: '10px' }}>
          <SlotInput which="a" />
          <div style={{ display: 'flex', alignItems: 'center', fontSize: '14px', fontWeight: '700', color: secondary, flexShrink: 0 }}>
            VS
          </div>
          <SlotInput which="b" />
        </div>

        {/* Comparison table */}
        {bothDone && rA && rB && (
          <>
            {/* Winner banner */}
            {winner !== 'tie' && (
              <div style={{
                background: isDark ? 'rgba(52,199,89,0.12)' : '#e8f8ed',
                border: '1.5px solid #34c759',
                borderRadius: '16px',
                padding: '14px 18px',
                textAlign: 'center',
              }}>
                <p style={{ fontSize: '16px', fontWeight: '700', color: '#34c759' }}>
                  ★ {winner === 'a' ? rA.product_name : rB.product_name} is the better choice
                </p>
                <p style={{ fontSize: '13px', color: isDark ? '#4cd964' : '#1a7a35', marginTop: '4px' }}>
                  Score {winner === 'a' ? rA.score : rB.score} vs {winner === 'a' ? rB.score : rA.score}
                  {(winner === 'a' ? rA.recalls.length : rB.recalls.length) === 0 &&
                   (winner === 'a' ? rB.recalls.length : rA.recalls.length) > 0
                    ? ' · No active recalls'
                    : ''}
                </p>
              </div>
            )}

            {winner === 'tie' && (
              <div style={{
                background: isDark ? 'rgba(255,159,10,0.1)' : '#fff8ed',
                border: '1.5px solid #ff9f0a',
                borderRadius: '16px', padding: '14px 18px', textAlign: 'center',
              }}>
                <p style={{ fontSize: '15px', fontWeight: '700', color: '#ff9f0a' }}>
                  It's a tie — both products score equally
                </p>
              </div>
            )}

            {/* Stats table */}
            <div style={{ background: cardBg, borderRadius: '18px', padding: '16px', boxShadow: shadow, display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {/* Column headers */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <p style={{ flex: 1, textAlign: 'center', fontSize: '12px', fontWeight: '700', color: primary }}>
                  {rA.product_name.split(' ').slice(0, 3).join(' ')}
                </p>
                <div style={{ width: '90px', flexShrink: 0 }} />
                <p style={{ flex: 1, textAlign: 'center', fontSize: '12px', fontWeight: '700', color: primary }}>
                  {rB.product_name.split(' ').slice(0, 3).join(' ')}
                </p>
              </div>

              <CompareRow label="Safety Score"   valA={rA.score}  valB={rB.score}  higher="better" />
              <CompareRow label="Grade"           valA={GRADE_RANK[rA.grade]} valB={GRADE_RANK[rB.grade]} higher="better"
                          unit="" />
              <CompareRow label="✅ Safe"          valA={safeA}    valB={safeB}    higher="better" />
              <CompareRow label="⚠️ Caution"       valA={cautionA} valB={cautionB} higher="worse"  />
              <CompareRow label="🚫 Avoid"          valA={avoidA}   valB={avoidB}   higher="worse"  />
              <CompareRow label="Ingredients"     valA={rA.ingredients_analysis.length} valB={rB.ingredients_analysis.length} higher="neutral" />
              <CompareRow label="🚨 Recalls"        valA={rA.recalls.length} valB={rB.recalls.length} higher="worse" />

              {/* Grade display row (text) */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                background: rowBg, borderRadius: '12px', padding: '2px 8px', marginTop: '4px',
              }}>
                <div style={{ flex: 1, textAlign: 'center' }}>
                  <span style={{
                    display: 'inline-block', padding: '4px 14px', borderRadius: '8px',
                    background: GRADE_COLOR[rA.grade] + '22',
                    color: GRADE_COLOR[rA.grade], fontSize: '16px', fontWeight: '800',
                  }}>{rA.grade}</span>
                </div>
                <p style={{ width: '90px', textAlign: 'center', fontSize: '11px', color: secondary, fontWeight: '600', flexShrink: 0 }}>
                  Grade
                </p>
                <div style={{ flex: 1, textAlign: 'center' }}>
                  <span style={{
                    display: 'inline-block', padding: '4px 14px', borderRadius: '8px',
                    background: GRADE_COLOR[rB.grade] + '22',
                    color: GRADE_COLOR[rB.grade], fontSize: '16px', fontWeight: '800',
                  }}>{rB.grade}</span>
                </div>
              </div>
            </div>

            {/* Concerns comparison */}
            {(avoidA > 0 || avoidB > 0) && (
              <div style={{ background: cardBg, borderRadius: '18px', padding: '16px', boxShadow: shadow }}>
                <p style={{ fontSize: '13px', fontWeight: '600', color: secondary, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: '12px' }}>
                  Ingredients to Avoid
                </p>
                <div style={{ display: 'flex', gap: '10px' }}>
                  {[{ r: rA, avoid: avoidA }, { r: rB, avoid: avoidB }].map(({ r, avoid }, idx) => (
                    <div key={idx} style={{ flex: 1 }}>
                      <p style={{ fontSize: '11px', fontWeight: '700', color: primary, marginBottom: '6px' }}>
                        {r.product_name.split(' ').slice(0, 2).join(' ')}
                      </p>
                      {avoid === 0 ? (
                        <p style={{ fontSize: '12px', color: '#34c759' }}>None ✓</p>
                      ) : (
                        r.ingredients_analysis
                          .filter(i => i.safety_level === 'avoid')
                          .slice(0, 4)
                          .map((ing, i) => (
                            <p key={i} style={{
                              fontSize: '11px', color: '#ff3b30',
                              marginBottom: '3px', lineHeight: 1.3,
                            }}>
                              • {ing.name}
                            </p>
                          ))
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recalls */}
            {(rA.recalls.length > 0 || rB.recalls.length > 0) && (
              <div style={{
                background: isDark ? 'rgba(255,59,48,0.1)' : '#fff1f0',
                border: '1.5px solid #ff3b30',
                borderRadius: '16px', padding: '14px 16px',
              }}>
                <p style={{ fontSize: '13px', fontWeight: '700', color: '#ff3b30', marginBottom: '8px' }}>
                  🚨 Recall Alerts
                </p>
                {rA.recalls.length > 0 && (
                  <p style={{ fontSize: '12px', color: '#ff3b30', marginBottom: '4px' }}>
                    <strong>{rA.product_name.split(' ')[0]}:</strong> {rA.recalls.length} recall{rA.recalls.length > 1 ? 's' : ''}
                  </p>
                )}
                {rB.recalls.length > 0 && (
                  <p style={{ fontSize: '12px', color: '#ff3b30' }}>
                    <strong>{rB.product_name.split(' ')[0]}:</strong> {rB.recalls.length} recall{rB.recalls.length > 1 ? 's' : ''}
                  </p>
                )}
              </div>
            )}

            {/* Positives comparison */}
            <div style={{ background: cardBg, borderRadius: '18px', padding: '16px', boxShadow: shadow }}>
              <p style={{ fontSize: '13px', fontWeight: '600', color: secondary, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: '12px' }}>
                Highlights
              </p>
              <div style={{ display: 'flex', gap: '10px' }}>
                {[rA, rB].map((r, idx) => (
                  <div key={idx} style={{ flex: 1 }}>
                    <p style={{ fontSize: '11px', fontWeight: '700', color: primary, marginBottom: '6px' }}>
                      {r.product_name.split(' ').slice(0, 2).join(' ')}
                    </p>
                    {r.positive_points.slice(0, 3).map((p, i) => (
                      <p key={i} style={{ fontSize: '11px', color: '#34c759', marginBottom: '3px', lineHeight: 1.3 }}>
                        + {p}
                      </p>
                    ))}
                    {r.negative_points.slice(0, 2).map((p, i) => (
                      <p key={i} style={{ fontSize: '11px', color: '#ff3b30', marginBottom: '3px', lineHeight: 1.3 }}>
                        − {p}
                      </p>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {/* Hint when only one is loaded */}
        {(slotA.state === 'done') !== (slotB.state === 'done') && (
          <p style={{ fontSize: '13px', color: secondary, textAlign: 'center' }}>
            Enter a barcode for the second product to compare
          </p>
        )}
      </div>
    </div>
  )
}
