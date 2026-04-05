import React, { useState, useRef } from 'react'
import { submitProduct } from '../api'
import type { SubmissionResult } from '../types'

interface AddProductPageProps {
  onBack:      () => void
  onAnalyze:   (barcode: string) => void
  onSubmitted: () => void
  isDark?:     boolean
}

type PageState = 'form' | 'loading' | 'done' | 'error'

export default function AddProductPage({ onBack, onAnalyze, onSubmitted, isDark = false }: AddProductPageProps) {
  const [productFile,        setProductFile]        = useState<File | null>(null)
  const [ingredientsFile,    setIngredientsFile]    = useState<File | null>(null)
  const [barcode,            setBarcode]            = useState('')
  const [productType,        setProductType]        = useState<'unknown' | 'food' | 'cosmetic'>('unknown')
  const [manualIngredients,  setManualIngredients]  = useState('')
  const [pageState,          setPageState]          = useState<PageState>('form')
  const [result,             setResult]             = useState<SubmissionResult | null>(null)
  const [errorMsg,           setErrorMsg]           = useState('')

  const productInputRef     = useRef<HTMLInputElement>(null)
  const ingredientsInputRef = useRef<HTMLInputElement>(null)

  const bg         = isDark ? '#000'     : '#f5f5f7'
  const headerBg   = isDark ? '#1c1c1e'  : '#fff'
  const cardBg     = isDark ? '#1c1c1e'  : '#fff'
  const primary    = isDark ? '#f2f2f7'  : '#1c1c1e'
  const secondary  = '#8e8e93'
  const border     = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'
  const shadow     = isDark ? '0 1px 6px rgba(0,0,0,0.4)' : '0 1px 6px rgba(0,0,0,0.05)'
  const backBg     = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'
  const inputBg    = isDark ? '#2c2c2e'  : '#f5f5f7'
  const inputBorder = isDark ? 'rgba(255,255,255,0.1)' : '#e5e5ea'

  const canSubmit = productFile || ingredientsFile || barcode.trim() || manualIngredients.trim()

  async function handleSubmit() {
    if (!canSubmit) return
    setPageState('loading')
    setErrorMsg('')

    const form = new FormData()
    if (productFile)              form.append('product_image',      productFile)
    if (ingredientsFile)          form.append('ingredients_image',  ingredientsFile)
    if (barcode.trim())           form.append('barcode',            barcode.trim())
    if (manualIngredients.trim()) form.append('manual_ingredients', manualIngredients.trim())
    form.append('product_type', productType)

    try {
      const res = await submitProduct(form)
      setResult(res)
      setPageState('done')
      // If analysis was auto-triggered on the backend, go straight to submissions
      const finalBarcode = res.product.barcode || barcode.trim()
      if (finalBarcode) {
        onSubmitted()
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Unknown error')
      setPageState('error')
    }
  }

  function ImagePickerCard({
    label, emoji, file, onFile, inputRef,
  }: {
    label: string; emoji: string; file: File | null
    onFile: (f: File) => void; inputRef: React.RefObject<HTMLInputElement>
  }) {
    const preview = file ? URL.createObjectURL(file) : null
    return (
      <div
        onClick={() => inputRef.current?.click()}
        style={{
          flex: 1,
          background: cardBg,
          borderRadius: '16px',
          padding: '16px',
          boxShadow: shadow,
          cursor: 'pointer',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '10px',
          border: file ? '2px solid #34c759' : `2px dashed ${inputBorder}`,
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          capture="environment"
          style={{ display: 'none' }}
          onChange={e => { if (e.target.files?.[0]) onFile(e.target.files[0]) }}
        />
        {preview ? (
          <img
            src={preview}
            alt={label}
            style={{ width: '100%', height: '100px', objectFit: 'cover', borderRadius: '10px' }}
          />
        ) : (
          <div style={{
            width: '64px', height: '64px', borderRadius: '12px',
            background: isDark ? '#2c2c2e' : '#f0f0f5',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '28px',
          }}>
            {emoji}
          </div>
        )}
        <p style={{ fontSize: '13px', fontWeight: '600', color: file ? '#34c759' : secondary, textAlign: 'center' }}>
          {file ? file.name.slice(0, 20) : label}
        </p>
      </div>
    )
  }

  // ── Result screen ─────────────────────────────────────────────────────────
  if (pageState === 'done' && result) {
    const { product, ingredients, ready_for_analysis } = result
    const barcodeFinal = product.barcode || barcode.trim()

    return (
      <div style={{ minHeight: '100vh', background: bg }}>
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
              Product Extracted
            </span>
          </div>
        </div>

        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Product info */}
          <div style={{ background: cardBg, borderRadius: '18px', padding: '18px', boxShadow: shadow }}>
            <h2 style={{ fontSize: '13px', fontWeight: '600', color: secondary, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: '12px' }}>
              Extracted Product
            </h2>
            {[
              { label: 'Name',    value: product.product_name },
              { label: 'Brand',   value: product.brand },
              { label: 'Barcode', value: product.barcode },
              { label: 'Type',    value: product.product_type },
              { label: 'Confidence', value: `${Math.round(product.confidence * 100)}%` },
            ].map(({ label, value }) => value && (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '14px', color: secondary }}>{label}</span>
                <span style={{ fontSize: '14px', fontWeight: '600', color: primary }}>{value}</span>
              </div>
            ))}
            {product.notes && (
              <p style={{ fontSize: '13px', color: secondary, marginTop: '8px', fontStyle: 'italic' }}>
                {product.notes}
              </p>
            )}
          </div>

          {/* Ingredients */}
          {ingredients.length > 0 && (
            <div style={{ background: cardBg, borderRadius: '18px', padding: '18px', boxShadow: shadow }}>
              <h2 style={{ fontSize: '13px', fontWeight: '600', color: secondary, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: '12px' }}>
                {ingredients.length} Ingredients Parsed
              </h2>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {ingredients.slice(0, 30).map((ing, i) => (
                  <span key={i} style={{
                    fontSize: '12px', padding: '4px 10px', borderRadius: '20px',
                    background: ing.is_allergen
                      ? (isDark ? '#330d0a' : '#ffe8e6')
                      : (isDark ? '#2c2c2e' : '#f0f0f5'),
                    color: ing.is_allergen ? '#ff3b30' : secondary,
                  }}>
                    {ing.name}
                  </span>
                ))}
                {ingredients.length > 30 && (
                  <span style={{ fontSize: '12px', color: secondary }}>+{ingredients.length - 30} more</span>
                )}
              </div>
            </div>
          )}

          {/* CTA */}
          {ready_for_analysis && barcodeFinal ? (
            <button
              onClick={() => onAnalyze(barcodeFinal)}
              style={{
                width: '100%', padding: '16px', borderRadius: '16px', border: 'none',
                background: '#34c759', color: '#fff', fontSize: '16px', fontWeight: '600', cursor: 'pointer',
              }}
            >
              Analyze Safety Now
            </button>
          ) : (
            <div style={{
              background: cardBg, borderRadius: '16px', padding: '16px',
              boxShadow: shadow, textAlign: 'center',
            }}>
              <p style={{ fontSize: '14px', color: secondary }}>
                {barcodeFinal
                  ? 'Product submitted. A barcode is needed to run analysis.'
                  : 'No barcode found. Enter one manually to run analysis.'}
              </p>
              {!barcodeFinal && (
                <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
                  <input
                    type="text"
                    placeholder="Enter barcode"
                    onChange={e => setBarcode(e.target.value)}
                    style={{
                      flex: 1, padding: '12px 14px', borderRadius: '12px',
                      border: `1px solid ${inputBorder}`, background: inputBg,
                      color: primary, fontSize: '15px', outline: 'none',
                    }}
                  />
                  <button
                    onClick={() => barcode.trim() && onAnalyze(barcode.trim())}
                    style={{
                      padding: '12px 16px', borderRadius: '12px', border: 'none',
                      background: '#34c759', color: '#fff', fontWeight: '600', cursor: 'pointer',
                    }}
                  >
                    Go
                  </button>
                </div>
              )}
            </div>
          )}

          <button
            onClick={onBack}
            style={{
              width: '100%', padding: '14px', borderRadius: '16px',
              border: `1px solid ${inputBorder}`, background: 'transparent',
              color: primary, fontSize: '15px', fontWeight: '600', cursor: 'pointer',
            }}
          >
            Back to Scanner
          </button>
        </div>
      </div>
    )
  }

  // ── Form screen ───────────────────────────────────────────────────────────
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
            Add Product
          </span>
        </div>
      </div>

      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <p style={{ fontSize: '14px', color: secondary, textAlign: 'center', lineHeight: 1.6 }}>
          Take photos of the product and its ingredient list. Claude will extract the data and run a safety analysis.
        </p>

        {/* Photo pickers */}
        <div style={{ display: 'flex', gap: '12px' }}>
          <ImagePickerCard
            label="Product Photo"
            emoji="📦"
            file={productFile}
            onFile={setProductFile}
            inputRef={productInputRef}
          />
          <ImagePickerCard
            label="Ingredients Photo"
            emoji="📋"
            file={ingredientsFile}
            onFile={setIngredientsFile}
            inputRef={ingredientsInputRef}
          />
        </div>

        {/* Manual ingredients */}
        <div style={{ background: cardBg, borderRadius: '16px', padding: '16px', boxShadow: shadow }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <p style={{ fontSize: '13px', fontWeight: '600', color: secondary }}>
              Ingredients (manual)
            </p>
            {manualIngredients.trim() && (
              <span style={{ fontSize: '12px', color: '#34c759', fontWeight: '600' }}>
                {manualIngredients.split(/[,\n;]+/).filter(s => s.trim()).length} entered
              </span>
            )}
          </div>
          <textarea
            value={manualIngredients}
            onChange={e => setManualIngredients(e.target.value)}
            placeholder={'Water, Glycerin, Niacinamide, Cetyl Alcohol...\n\nSeparate by comma or new line'}
            rows={5}
            style={{
              width: '100%',
              padding: '12px 14px',
              borderRadius: '12px',
              border: `1px solid ${manualIngredients.trim() ? '#34c759' : inputBorder}`,
              background: inputBg,
              color: primary,
              fontSize: '14px',
              outline: 'none',
              resize: 'vertical',
              fontFamily: 'inherit',
              lineHeight: 1.5,
              boxSizing: 'border-box',
            }}
          />
          <p style={{ fontSize: '11px', color: secondary, marginTop: '6px' }}>
            Overrides the ingredient photo if both are provided.
          </p>
        </div>

        {/* Barcode */}
        <div style={{ background: cardBg, borderRadius: '16px', padding: '16px', boxShadow: shadow }}>
          <p style={{ fontSize: '13px', fontWeight: '600', color: secondary, marginBottom: '10px' }}>
            Barcode (optional — extracted from photo if not provided)
          </p>
          <input
            type="text"
            inputMode="numeric"
            value={barcode}
            onChange={e => setBarcode(e.target.value)}
            placeholder="e.g. 3017620422003"
            style={{
              width: '100%', padding: '12px 14px', borderRadius: '12px',
              border: `1px solid ${inputBorder}`, background: inputBg,
              color: primary, fontSize: '15px', outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Product type */}
        <div style={{ background: cardBg, borderRadius: '16px', padding: '16px', boxShadow: shadow }}>
          <p style={{ fontSize: '13px', fontWeight: '600', color: secondary, marginBottom: '10px' }}>
            Product Type
          </p>
          <div style={{ display: 'flex', gap: '8px' }}>
            {(['unknown', 'food', 'cosmetic'] as const).map(t => (
              <button
                key={t}
                onClick={() => setProductType(t)}
                style={{
                  flex: 1, padding: '10px', borderRadius: '12px', border: 'none',
                  background: productType === t ? '#34c759' : (isDark ? '#2c2c2e' : '#f0f0f5'),
                  color: productType === t ? '#fff' : primary,
                  fontSize: '14px', fontWeight: '600', cursor: 'pointer', textTransform: 'capitalize',
                }}
              >
                {t === 'unknown' ? 'Auto' : t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {pageState === 'error' && (
          <p style={{ fontSize: '14px', color: '#ff3b30', textAlign: 'center' }}>{errorMsg}</p>
        )}

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!canSubmit || pageState === 'loading'}
          style={{
            width: '100%', padding: '16px', borderRadius: '16px', border: 'none',
            background: canSubmit ? '#34c759' : (isDark ? '#2c2c2e' : '#e5e5ea'),
            color: canSubmit ? '#fff' : secondary,
            fontSize: '16px', fontWeight: '600',
            cursor: canSubmit ? 'pointer' : 'not-allowed',
          }}
        >
          {pageState === 'loading' ? 'Analyzing photos...' : 'Extract & Analyze'}
        </button>
      </div>
    </div>
  )
}
