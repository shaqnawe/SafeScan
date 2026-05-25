import React, { useState, useRef } from 'react'
import { ArrowLeft, AlertTriangle } from 'lucide-react'
import { submitProduct } from '../api'
import type { SubmissionResult } from '../types'
import ThemeToggle from './ThemeToggle'
import { getTheme, glassStyle, FONT_STACK } from '../theme'

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

  const theme      = getTheme(isDark)
  const primary    = theme.primary
  const secondary  = theme.tertiary
  const backBg     = theme.ingredientBg
  const inputBg    = theme.ingredientBg
  const inputBorder = theme.glassBorder
  const headerStyle: React.CSSProperties = {
    ...glassStyle(theme),
    borderRadius: 0,
    borderLeft: 'none',
    borderRight: 'none',
    borderTop: 'none',
    boxShadow: 'none',
  }
  const cardStyle: React.CSSProperties = {
    ...glassStyle(theme),
    borderRadius: 18,
  }
  const rootStyle: React.CSSProperties = {
    minHeight: '100vh',
    background: theme.bg,
    backgroundImage: theme.bgGradient,
    color: theme.primary,
    fontFamily: FONT_STACK,
  }

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
      // If analysis was auto-triggered on the backend, go straight to submissions —
      // unless extraction had a failure the user should see + decide what to do about.
      const finalBarcode = res.product.barcode || barcode.trim()
      const extractionHadIssues =
        res.product_status === 'failed' || res.ingredients_status === 'failed'
      if (finalBarcode && !extractionHadIssues) {
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
          ...cardStyle,
          borderRadius: '16px',
          padding: '16px',
          boxShadow: theme.glassShadow,
          cursor: 'pointer',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '10px',
          border: file ? `2px solid ${theme.accent}` : `2px dashed ${inputBorder}`,
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
            background: theme.ingredientBg,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '28px',
          }}>
            {emoji}
          </div>
        )}
        <p style={{ fontSize: '13px', fontWeight: '600', color: file ? theme.accent : secondary, textAlign: 'center' }}>
          {file ? file.name.slice(0, 20) : label}
        </p>
      </div>
    )
  }

  // ── Result screen ─────────────────────────────────────────────────────────
  if (pageState === 'done' && result) {
    const { product, ingredients, ready_for_analysis, product_status, ingredients_status } = result
    const barcodeFinal = product.barcode || barcode.trim()

    const failedCalls: string[] = []
    if (product_status === 'failed')     failedCalls.push('product label')
    if (ingredients_status === 'failed') failedCalls.push('ingredient list')

    return (
      <div style={rootStyle}>
        <div style={{
          ...headerStyle,
          padding: '20px 20px 16px', position: 'sticky', top: 0, zIndex: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <button onClick={onBack} className="press" style={{
              background: backBg, border: 'none', borderRadius: '50%',
              width: '36px', height: '36px', cursor: 'pointer', color: primary,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }} aria-label="Back">
              <ArrowLeft size={16} strokeWidth={2} aria-hidden />
            </button>
            <span style={{ flex: 1, textAlign: 'center', fontSize: '17px', fontWeight: '700', color: primary }}>
              Product Extracted
            </span>
            <ThemeToggle variant="icon" />
          </div>
        </div>

        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Extraction-failure warning — surfaces backend product_status / ingredients_status.
              We tell the user what didn't read cleanly so they can retake the relevant photo. */}
          {failedCalls.length > 0 && (
            <div className="fade-up" style={{
              ...cardStyle,
              padding: '14px 16px',
              background: theme.redSoft,
              border: `1px solid ${theme.red}55`,
              display: 'flex',
              alignItems: 'flex-start',
              gap: '12px',
            }}>
              <AlertTriangle size={20} strokeWidth={2} aria-hidden style={{ color: theme.red, flexShrink: 0, marginTop: 2 }} />
              <div style={{ minWidth: 0 }}>
                <p style={{ fontSize: '14px', fontWeight: '700', color: theme.red, marginBottom: 4 }}>
                  Couldn&apos;t read the {failedCalls.join(' or ')}
                </p>
                <p style={{ fontSize: '13px', color: theme.secondary, lineHeight: 1.4 }}>
                  Try retaking the photo in better lighting, holding the camera closer, or entering the data manually.
                </p>
              </div>
            </div>
          )}

          {/* Product info */}
          <div style={{ ...cardStyle, padding: '20px' }}>
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
            <div style={{ ...cardStyle, padding: '20px' }}>
              <h2 style={{ fontSize: '13px', fontWeight: '600', color: secondary, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: '12px' }}>
                {ingredients.length} Ingredients Parsed
              </h2>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {ingredients.slice(0, 30).map((ing, i) => (
                  <span key={i} style={{
                    fontSize: '12px', padding: '4px 10px', borderRadius: '20px',
                    background: ing.is_allergen
                      ? theme.redSoft
                      : theme.ingredientBg,
                    color: ing.is_allergen ? theme.red : secondary,
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
                background: theme.gradeGradient, color: theme.btnText, fontSize: '16px', fontWeight: '600', cursor: 'pointer',
              }}
            >
              Analyze Safety Now
            </button>
          ) : (
            <div style={{
              ...cardStyle, padding: '16px',
              boxShadow: theme.glassShadow, textAlign: 'center',
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
                      background: theme.gradeGradient, color: theme.btnText, fontWeight: '600', cursor: 'pointer',
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
    <div style={rootStyle}>
      {/* Header */}
      <div style={{
        ...headerStyle,
        padding: '20px 20px 16px', position: 'sticky', top: 0, zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button onClick={onBack} className="press" style={{
            background: backBg, border: 'none', borderRadius: '50%',
            width: '36px', height: '36px', cursor: 'pointer', color: primary,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }} aria-label="Back">
            <ArrowLeft size={16} strokeWidth={2} aria-hidden />
          </button>
          <span style={{ flex: 1, textAlign: 'center', fontSize: '17px', fontWeight: '700', color: primary }}>
            Add Product
          </span>
          <ThemeToggle variant="icon" />
        </div>
      </div>

      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <p className="fade-up stagger-1" style={{ fontSize: '14px', color: secondary, textAlign: 'center', lineHeight: 1.6 }}>
          Take photos of the product and its ingredient list. Claude will extract the data and run a safety analysis.
        </p>

        {/* Photo pickers */}
        <div className="fade-up stagger-2" style={{ display: 'flex', gap: '12px' }}>
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
        <div style={{ ...cardStyle, padding: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <p style={{ fontSize: '13px', fontWeight: '600', color: secondary }}>
              Ingredients (manual)
            </p>
            {manualIngredients.trim() && (
              <span style={{ fontSize: '12px', color: theme.accent, fontWeight: '600' }}>
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
        <div style={{ ...cardStyle, padding: '16px' }}>
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
        <div style={{ ...cardStyle, padding: '16px' }}>
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
                  background: productType === t ? theme.gradeGradient : theme.ingredientBg,
                  color: productType === t ? theme.btnText : primary,
                  fontSize: '14px', fontWeight: '600', cursor: 'pointer', textTransform: 'capitalize',
                }}
              >
                {t === 'unknown' ? 'Auto' : t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {pageState === 'error' && (
          <p style={{ fontSize: '14px', color: theme.red, textAlign: 'center' }}>{errorMsg}</p>
        )}

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!canSubmit || pageState === 'loading'}
          style={{
            width: '100%', padding: '16px', borderRadius: '16px', border: 'none',
            background: canSubmit ? theme.gradeGradient : theme.ingredientBg,
            color: canSubmit ? theme.btnText : secondary,
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
