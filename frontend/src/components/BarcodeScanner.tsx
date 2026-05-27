import React, { useState, useRef, useEffect } from 'react'
import { Capacitor } from '@capacitor/core'
import { BarcodeScanner as NativeScanner, BarcodeFormat } from '@capacitor-mlkit/barcode-scanning'
import { Haptics, ImpactStyle } from '@capacitor/haptics'
import { useZxing } from 'react-zxing'
import type { ScanHistoryEntry } from '../hooks/useScanHistory'
import type { SearchResult } from '../types'
import { searchProducts } from '../api'
import { FONT_STACK } from '../theme'

// Camera UI stays dark regardless of OS theme — it's a fullscreen viewfinder
// surface, so the chrome around it is always the dark glassmorphism variant.
const ACCENT          = '#fbbf24'  // amber
const ACCENT_GRADIENT = 'linear-gradient(135deg, #fbbf24, #f59e0b)'
void FONT_STACK // re-exposed via inline style if needed later

const GRADE_COLOR: Record<string, string> = {
  A: '#22c55e', B: '#84cc16', C: '#f59e0b', D: '#ef4444'
}

const IS_NATIVE = Capacitor.isNativePlatform()

interface BarcodeScannerProps {
  onScan: (barcode: string) => void
  history?: ScanHistoryEntry[]
  onViewHistory?: () => void
  onAddProduct?: () => void
  onViewSubmissions?: () => void
  onCompare?: () => void
}

// ─── Native scanner (iOS / Android) ─────────────────────────────────────────

function NativeScannerView({ onScan }: { onScan: (barcode: string) => void }) {
  const [scanning, setScanning] = useState(false)
  const [scannerError, setScannerError] = useState<string | null>(null)
  const [lastScanned, setLastScanned] = useState<string | null>(null)

  const handleScan = async () => {
    setScannerError(null)
    setScanning(true)
    try {
      const { camera } = await NativeScanner.checkPermissions()
      if (camera !== 'granted') {
        const result = await NativeScanner.requestPermissions()
        if (result.camera !== 'granted') {
          setScannerError('Camera permission denied. Enable it in Settings.')
          setScanning(false)
          return
        }
      }

      const { barcodes } = await NativeScanner.scan({
        formats: [BarcodeFormat.Ean13, BarcodeFormat.UpcA, BarcodeFormat.Ean8],
      })

      if (barcodes.length > 0) {
        const value = barcodes[0].rawValue ?? ''
        if (!value) return
        setLastScanned(value)
        await Haptics.impact({ style: ImpactStyle.Medium })
        onScan(value)
      }
    } catch (err) {
      const msg = String(err)
      if (!msg.includes('cancel') && !msg.includes('dismiss')) {
        setScannerError('Scanner unavailable. Use manual entry below.')
      }
    } finally {
      setScanning(false)
    }
  }

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '20px',
      padding: '40px 24px',
      minHeight: '300px',
    }}>
      <button
        onClick={handleScan}
        disabled={scanning}
        style={{
          width: '160px',
          height: '160px',
          borderRadius: '80px',
          border: `3px solid ${scanning ? 'rgba(251,191,36,0.4)' : ACCENT}`,
          background: scanning ? 'rgba(251,191,36,0.1)' : 'rgba(251,191,36,0.15)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: scanning ? 'default' : 'pointer',
          gap: '8px',
          transition: 'all 0.2s',
        }}
      >
        <span style={{ fontSize: '52px' }}>{scanning ? '⏳' : '📷'}</span>
        <span style={{
          color: scanning ? 'rgba(251,191,36,0.6)' : ACCENT,
          fontSize: '13px',
          fontWeight: '600',
        }}>
          {scanning ? 'Scanning…' : 'Tap to Scan'}
        </span>
      </button>

      {lastScanned && !scanning && (
        <div style={{
          background: 'rgba(251,191,36,0.15)',
          border: '1px solid rgba(251,191,36,0.4)',
          borderRadius: '12px',
          padding: '10px 20px',
          color: ACCENT,
          fontSize: '13px',
          fontWeight: '600',
        }}>
          Scanned: {lastScanned}
        </div>
      )}

      {scannerError && (
        <p style={{
          color: '#ff3b30',
          fontSize: '13px',
          textAlign: 'center',
          maxWidth: '260px',
        }}>
          {scannerError}
        </p>
      )}
    </div>
  )
}

// ─── Web scanner (ZXing camera) ──────────────────────────────────────────────

function WebScannerView({ onScan }: { onScan: (barcode: string) => void }) {
  const [scannerError, setScannerError] = useState<string | null>(null)
  const [cameraActive, setCameraActive] = useState(true)
  const [lastScanned, setLastScanned] = useState<string | null>(null)
  const lastScanTime = useRef<number>(0)

  const { ref } = useZxing({
    paused: !cameraActive,
    constraints: {
      video: {
        width:     { ideal: 1920 },
        height:    { ideal: 1080 },
        facingMode: { ideal: 'environment' },
        // @ts-expect-error — non-standard but honored by Chromium-based browsers
        focusMode: { ideal: 'continuous' },
      },
      audio: false,
    },
    onDecodeResult(result) {
      const now = Date.now()
      const text = result.getText()
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

  return (
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
            <div style={{ width: '260px', height: '160px', position: 'relative' }}>
              {[
                { top: 0, left: 0, borderTop: '3px solid #fbbf24', borderLeft: '3px solid #fbbf24' },
                { top: 0, right: 0, borderTop: '3px solid #fbbf24', borderRight: '3px solid #fbbf24' },
                { bottom: 0, left: 0, borderBottom: '3px solid #fbbf24', borderLeft: '3px solid #fbbf24' },
                { bottom: 0, right: 0, borderBottom: '3px solid #fbbf24', borderRight: '3px solid #fbbf24' },
              ].map((style, i) => (
                <div key={i} style={{
                  position: 'absolute',
                  width: '28px',
                  height: '28px',
                  borderRadius: '2px',
                  ...style,
                }} />
              ))}
              <div style={{
                position: 'absolute',
                left: '10px',
                right: '10px',
                top: '50%',
                height: '2px',
                background: 'linear-gradient(90deg, transparent, #fbbf24, transparent)',
                animation: 'scanline 2s ease-in-out infinite',
              }} />
            </div>
          </div>

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
        <div style={{ textAlign: 'center', color: 'rgba(255,255,255,0.7)', padding: '40px' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>📷</div>
          <p style={{ fontSize: '16px', marginBottom: '8px' }}>
            {scannerError || 'Camera unavailable'}
          </p>
          <p style={{ fontSize: '13px', opacity: 0.6 }}>Use the manual input below</p>
        </div>
      )}

      {lastScanned && (
        <div style={{
          position: 'absolute',
          top: '16px',
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'rgba(251,191,36,0.9)',
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
  )
}

// ─── Main component ──────────────────────────────────────────────────────────

export default function BarcodeScanner({
  onScan,
  history = [],
  onViewHistory,
  onAddProduct,
  onViewSubmissions,
  onCompare,
}: BarcodeScannerProps) {
  const [manualBarcode, setManualBarcode] = useState('')
  const [searchQuery,   setSearchQuery]   = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [isSearching,   setIsSearching]   = useState(false)

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = manualBarcode.trim()
    if (trimmed) onScan(trimmed)
  }

  // Debounced name search. Cancels in-flight on each keystroke via AbortController.
  useEffect(() => {
    const q = searchQuery.trim()
    if (q.length < 2) { setSearchResults([]); setIsSearching(false); return }
    const controller = new AbortController()
    const t = setTimeout(async () => {
      setIsSearching(true)
      try {
        const rows = await searchProducts(q, controller.signal)
        setSearchResults(rows)
      } catch (err) {
        if ((err as Error).name !== 'AbortError') setSearchResults([])
      } finally {
        setIsSearching(false)
      }
    }, 300)
    return () => { clearTimeout(t); controller.abort() }
  }, [searchQuery])

  return (
    <div style={{ minHeight: '100vh', background: '#000', display: 'flex', flexDirection: 'column' }}>
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
          <h1 style={{ color: '#fff', fontSize: '22px', fontWeight: '700', letterSpacing: '-0.3px' }}>
            SafeScan
          </h1>
          <div style={{ position: 'absolute', right: 0, display: 'flex', gap: '8px' }}>
            {onCompare && (
              <button
                onClick={onCompare}
                style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: '50%', width: '36px', height: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', fontSize: '16px' }}
                title="Compare products"
              >⚖️</button>
            )}
            {onViewSubmissions && (
              <button
                onClick={onViewSubmissions}
                style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: '50%', width: '36px', height: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', fontSize: '16px' }}
                title="My submissions"
              >📦</button>
            )}
            {onAddProduct && (
              <button
                onClick={onAddProduct}
                style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: '50%', width: '36px', height: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', fontSize: '18px' }}
                title="Add product manually"
              >+</button>
            )}
            {onViewHistory && (
              <button
                onClick={onViewHistory}
                style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: '50%', width: '36px', height: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', fontSize: '16px' }}
                title="Scan history"
              >🕐</button>
            )}
          </div>
        </div>
        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px' }}>
          Scan a barcode to check product safety
        </p>
      </div>

      {/* Camera / scan area */}
      {IS_NATIVE ? <NativeScannerView onScan={onScan} /> : <WebScannerView onScan={onScan} />}

      {/* Manual input + history */}
      <div style={{
        background: '#1c1c1e',
        padding: '20px 24px 32px',
        borderTop: '1px solid rgba(255,255,255,0.1)',
      }}>
        {/* Name search */}
        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '12px', textAlign: 'center' }}>
          Search by name or brand
        </p>
        <input
          type="text"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="e.g. cetaphil, diet coke, sriracha"
          style={{
            width: '100%',
            padding: '14px 16px',
            borderRadius: '12px',
            border: '1px solid rgba(255,255,255,0.15)',
            background: 'rgba(255,255,255,0.08)',
            color: '#fff',
            fontSize: '16px',
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />

        {searchQuery.trim().length >= 2 && (
          <div
            style={{
              marginTop: 10,
              maxHeight: 280,
              overflowY: 'auto',
              background: 'rgba(0,0,0,0.4)',
              borderRadius: 12,
              border: '1px solid rgba(255,255,255,0.08)',
            }}
          >
            {isSearching && searchResults.length === 0 && (
              <div style={{ padding: 14, color: 'rgba(255,255,255,0.5)', fontSize: 13, textAlign: 'center' }}>
                Searching…
              </div>
            )}
            {!isSearching && searchResults.length === 0 && (
              <div style={{ padding: 14, color: 'rgba(255,255,255,0.5)', fontSize: 13, textAlign: 'center' }}>
                No products match "{searchQuery.trim()}"
              </div>
            )}
            {searchResults.map(r => (
              <button
                key={r.barcode}
                onClick={() => onScan(r.barcode)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  width: '100%',
                  padding: '12px 14px',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: '1px solid rgba(255,255,255,0.05)',
                  cursor: 'pointer',
                  textAlign: 'left',
                  color: '#fff',
                  fontFamily: 'inherit',
                }}
              >
                {r.image_url ? (
                  <img
                    src={r.image_url}
                    alt=""
                    style={{
                      width: 38, height: 38, borderRadius: 6, objectFit: 'contain',
                      background: 'rgba(255,255,255,0.04)', flexShrink: 0, padding: 2,
                    }}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                ) : (
                  <div style={{
                    width: 38, height: 38, borderRadius: 6,
                    background: 'rgba(255,255,255,0.04)', flexShrink: 0,
                  }} />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  {r.brand && (
                    <div style={{
                      fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
                      textTransform: 'uppercase', color: 'rgba(255,255,255,0.5)',
                    }}>
                      {r.brand}
                    </div>
                  )}
                  <div style={{
                    fontSize: 13, fontWeight: 500, color: '#fff', marginTop: 2,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {r.name}
                  </div>
                </div>
                <span style={{
                  fontSize: 10, color: 'rgba(255,255,255,0.4)',
                  textTransform: 'uppercase', letterSpacing: '0.1em', flexShrink: 0,
                }}>
                  {r.product_type}
                </span>
              </button>
            ))}
          </div>
        )}

        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.8px', marginTop: '20px', marginBottom: '12px', textAlign: 'center' }}>
          Or enter barcode manually
        </p>
        <form onSubmit={handleManualSubmit} style={{ display: 'flex', gap: '10px' }}>
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
              background: manualBarcode.trim() ? ACCENT_GRADIENT : 'rgba(255,255,255,0.1)',
              color: manualBarcode.trim() ? '#0a0a0f' : 'rgba(255,255,255,0.4)',
              fontSize: '15px',
              fontWeight: '700',
              cursor: manualBarcode.trim() ? 'pointer' : 'not-allowed',
              transition: 'background 0.2s',
              whiteSpace: 'nowrap',
              boxShadow: manualBarcode.trim() ? '0 4px 16px rgba(251,191,36,0.3)' : 'none',
            }}
          >
            Scan
          </button>
        </form>

        {history.length > 0 && (
          <div style={{ marginTop: '20px' }}>
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '10px', textAlign: 'center' }}>
              Recent Scans
            </p>
            <div style={{ display: 'flex', gap: '10px', overflowX: 'auto', paddingBottom: '4px', scrollbarWidth: 'none' }}>
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
