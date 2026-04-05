import React, { useState, useRef } from 'react'
import { useZxing } from 'react-zxing'
import type { ScanHistoryEntry } from '../hooks/useScanHistory'

const GRADE_COLOR: Record<string, string> = {
  A: '#34c759', B: '#a3d977', C: '#ff9f0a', D: '#ff3b30', E: '#9c2b2b',
}

interface BarcodeScannerProps {
  onScan: (barcode: string) => void
  history?: ScanHistoryEntry[]
  onViewHistory?: () => void
  onAddProduct?: () => void
  onViewSubmissions?: () => void
  onCompare?: () => void
}

export default function BarcodeScanner({ onScan, history = [], onViewHistory, onAddProduct, onViewSubmissions, onCompare }: BarcodeScannerProps) {
  const [manualBarcode, setManualBarcode] = useState('')
  const [scannerError, setScannerError] = useState<string | null>(null)
  const [lastScanned, setLastScanned] = useState<string | null>(null)
  const [cameraActive, setCameraActive] = useState(true)
  const lastScanTime = useRef<number>(0)

  const { ref } = useZxing({
    paused: !cameraActive,
    onDecodeResult(result) {
      const now = Date.now()
      const text = result.getText()
      // Debounce: ignore scans within 2s of the last one
      if (text && now - lastScanTime.current > 2000) {
        lastScanTime.current = now
        setLastScanned(text)
        setTimeout(() => onScan(text), 300)
      }
    },
    onError(error) {
      const msg = String(error)
      if (!msg.includes('NotFoundException')) {
        setScannerError('Camera access denied or not available')
        setCameraActive(false)
      }
    },
  })

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = manualBarcode.trim()
    if (trimmed) {
      onScan(trimmed)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: '#000',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        background: 'rgba(0,0,0,0.8)',
        padding: '20px 24px 16px',
        textAlign: 'center',
        zIndex: 10,
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '10px',
          marginBottom: '4px',
          position: 'relative',
        }}>
          <span style={{ fontSize: '28px' }}>🔍</span>
          <h1 style={{
            color: '#fff',
            fontSize: '22px',
            fontWeight: '700',
            letterSpacing: '-0.3px',
          }}>
            SafeScan
          </h1>
          <div style={{ position: 'absolute', right: 0, display: 'flex', gap: '8px' }}>
            {onCompare && (
              <button
                onClick={onCompare}
                style={{
                  background: 'rgba(255,255,255,0.1)',
                  border: 'none', borderRadius: '50%',
                  width: '36px', height: '36px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', fontSize: '16px',
                }}
                title="Compare products"
              >
                ⚖️
              </button>
            )}
            {onViewSubmissions && (
              <button
                onClick={onViewSubmissions}
                style={{
                  background: 'rgba(255,255,255,0.1)',
                  border: 'none', borderRadius: '50%',
                  width: '36px', height: '36px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', fontSize: '16px',
                }}
                title="My submissions"
              >
                📦
              </button>
            )}
            {onAddProduct && (
              <button
                onClick={onAddProduct}
                style={{
                  background: 'rgba(255,255,255,0.1)',
                  border: 'none', borderRadius: '50%',
                  width: '36px', height: '36px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', fontSize: '18px',
                }}
                title="Add product manually"
              >
                +
              </button>
            )}
            {onViewHistory && (
              <button
                onClick={onViewHistory}
                style={{
                  background: 'rgba(255,255,255,0.1)',
                  border: 'none', borderRadius: '50%',
                  width: '36px', height: '36px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', fontSize: '16px',
                }}
                title="Scan history"
              >
                🕐
              </button>
            )}
          </div>
        </div>
        <p style={{
          color: 'rgba(255,255,255,0.6)',
          fontSize: '13px',
        }}>
          Scan a barcode to check product safety
        </p>
      </div>

      {/* Camera view */}
      <div style={{
        flex: 1,
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '300px',
        overflow: 'hidden',
      }}>
        {cameraActive && !scannerError ? (
          <>
            <video
              ref={ref as React.RefObject<HTMLVideoElement>}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                position: 'absolute',
                inset: 0,
              }}
            />
            {/* Scanning overlay */}
            <div style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              pointerEvents: 'none',
            }}>
              <div style={{
                width: '260px',
                height: '160px',
                position: 'relative',
              }}>
                {/* Corner markers */}
                {[
                  { top: 0, left: 0, borderTop: '3px solid #34c759', borderLeft: '3px solid #34c759' },
                  { top: 0, right: 0, borderTop: '3px solid #34c759', borderRight: '3px solid #34c759' },
                  { bottom: 0, left: 0, borderBottom: '3px solid #34c759', borderLeft: '3px solid #34c759' },
                  { bottom: 0, right: 0, borderBottom: '3px solid #34c759', borderRight: '3px solid #34c759' },
                ].map((style, i) => (
                  <div key={i} style={{
                    position: 'absolute',
                    width: '28px',
                    height: '28px',
                    borderRadius: '2px',
                    ...style,
                  }} />
                ))}
                {/* Scan line */}
                <div style={{
                  position: 'absolute',
                  left: '10px',
                  right: '10px',
                  top: '50%',
                  height: '2px',
                  background: 'linear-gradient(90deg, transparent, #34c759, transparent)',
                  animation: 'scanline 2s ease-in-out infinite',
                }} />
              </div>
            </div>

            {/* Instruction text */}
            <div style={{
              position: 'absolute',
              bottom: '20px',
              left: 0,
              right: 0,
              textAlign: 'center',
            }}>
              <span style={{
                background: 'rgba(0,0,0,0.6)',
                color: '#fff',
                fontSize: '13px',
                padding: '6px 16px',
                borderRadius: '20px',
              }}>
                Point camera at a barcode
              </span>
            </div>
          </>
        ) : (
          <div style={{
            textAlign: 'center',
            color: 'rgba(255,255,255,0.7)',
            padding: '40px',
          }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>📷</div>
            <p style={{ fontSize: '16px', marginBottom: '8px' }}>
              {scannerError || 'Camera unavailable'}
            </p>
            <p style={{ fontSize: '13px', opacity: 0.6 }}>
              Use the manual input below
            </p>
          </div>
        )}

        {lastScanned && (
          <div style={{
            position: 'absolute',
            top: '16px',
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'rgba(52, 199, 89, 0.9)',
            color: '#fff',
            padding: '8px 20px',
            borderRadius: '20px',
            fontSize: '14px',
            fontWeight: '600',
            zIndex: 5,
          }}>
            Scanned: {lastScanned}
          </div>
        )}
      </div>

      {/* Manual input section */}
      <div style={{
        background: '#1c1c1e',
        padding: '20px 24px 32px',
        borderTop: '1px solid rgba(255,255,255,0.1)',
      }}>
        <p style={{
          color: 'rgba(255,255,255,0.5)',
          fontSize: '12px',
          textTransform: 'uppercase',
          letterSpacing: '0.8px',
          marginBottom: '12px',
          textAlign: 'center',
        }}>
          Or enter barcode manually
        </p>
        <form onSubmit={handleManualSubmit} style={{
          display: 'flex',
          gap: '10px',
        }}>
          <input
            type="text"
            value={manualBarcode}
            onChange={e => setManualBarcode(e.target.value)}
            placeholder="e.g. 3017620422003"
            inputMode="numeric"
            style={{
              flex: 1,
              padding: '14px 16px',
              borderRadius: '12px',
              border: '1px solid rgba(255,255,255,0.15)',
              background: 'rgba(255,255,255,0.08)',
              color: '#fff',
              fontSize: '16px',
              outline: 'none',
            }}
          />
          <button
            type="submit"
            disabled={!manualBarcode.trim()}
            style={{
              padding: '14px 20px',
              borderRadius: '12px',
              border: 'none',
              background: manualBarcode.trim() ? '#34c759' : 'rgba(255,255,255,0.1)',
              color: '#fff',
              fontSize: '15px',
              fontWeight: '600',
              cursor: manualBarcode.trim() ? 'pointer' : 'not-allowed',
              transition: 'background 0.2s',
              whiteSpace: 'nowrap',
            }}
          >
            Scan
          </button>
        </form>

        {/* Scan history */}
        {history.length > 0 && (
          <div style={{ marginTop: '20px' }}>
            <p style={{
              color: 'rgba(255,255,255,0.5)',
              fontSize: '12px',
              textTransform: 'uppercase',
              letterSpacing: '0.8px',
              marginBottom: '10px',
              textAlign: 'center',
            }}>
              Recent Scans
            </p>
            <div style={{
              display: 'flex',
              gap: '10px',
              overflowX: 'auto',
              paddingBottom: '4px',
              scrollbarWidth: 'none',
            }}>
              {history.map(entry => (
                <button
                  key={entry.barcode + entry.scanned_at}
                  onClick={() => onScan(entry.barcode)}
                  style={{
                    flexShrink: 0,
                    width: '100px',
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '12px',
                    padding: '10px 8px',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  {/* Thumbnail or emoji */}
                  <div style={{
                    width: '44px',
                    height: '44px',
                    borderRadius: '8px',
                    background: 'rgba(255,255,255,0.08)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    overflow: 'hidden',
                    flexShrink: 0,
                  }}>
                    {entry.image_url ? (
                      <img
                        src={entry.image_url}
                        alt={entry.name}
                        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                        onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                      />
                    ) : (
                      <span style={{ fontSize: '22px' }}>
                        {entry.product_type === 'food' ? '🛒' : '✨'}
                      </span>
                    )}
                  </div>

                  {/* Product name */}
                  <p style={{
                    fontSize: '11px',
                    color: 'rgba(255,255,255,0.75)',
                    textAlign: 'center',
                    lineHeight: 1.3,
                    overflow: 'hidden',
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    width: '100%',
                  }}>
                    {entry.name}
                  </p>

                  {/* Grade badge */}
                  <span style={{
                    fontSize: '11px',
                    fontWeight: '700',
                    color: GRADE_COLOR[entry.grade] || '#8e8e93',
                    background: 'rgba(255,255,255,0.08)',
                    borderRadius: '6px',
                    padding: '2px 8px',
                  }}>
                    {entry.grade} · {entry.score}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Example barcodes */}
        <div style={{ marginTop: '14px', textAlign: 'center' }}>
          <p style={{ color: 'rgba(255,255,255,0.35)', fontSize: '12px', marginBottom: '8px' }}>
            Try examples:
          </p>
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', flexWrap: 'wrap' }}>
            {[
              { label: 'Nutella', code: '3017620422003' },
              { label: 'Coca-Cola', code: '5449000000996' },
              { label: 'Kit Kat', code: '5000159461122' },
            ].map(({ label, code }) => (
              <button
                key={code}
                onClick={() => onScan(code)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '20px',
                  border: '1px solid rgba(255,255,255,0.2)',
                  background: 'transparent',
                  color: 'rgba(255,255,255,0.5)',
                  fontSize: '12px',
                  cursor: 'pointer',
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes scanline {
          0%, 100% { transform: translateY(-30px); opacity: 0.7; }
          50% { transform: translateY(30px); opacity: 1; }
        }
      `}</style>
    </div>
  )
}
