import { Capacitor } from '@capacitor/core'
import type { SafetyReport, SubmissionResult, UserSubmission, SearchResult } from './types'

// On native (iOS/Android), VITE_API_URL must be set to the production backend URL
// at build time (e.g. https://api.safescan.app). On web, fall back to localhost.
const API_BASE = Capacitor.isNativePlatform()
  ? (import.meta.env.VITE_API_URL as string)
  : (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8000'

export async function scanBarcode(barcode: string): Promise<SafetyReport> {
  const response = await fetch(`${API_BASE}/api/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ barcode }),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP error ${response.status}`)
  }

  return response.json()
}

export async function getSubmissions(): Promise<UserSubmission[]> {
  const response = await fetch(`${API_BASE}/api/submissions`)
  if (!response.ok) throw new Error(`HTTP error ${response.status}`)
  return response.json()
}

export async function searchProducts(
  query: string,
  signal?: AbortSignal,
): Promise<SearchResult[]> {
  const url = `${API_BASE}/api/search?q=${encodeURIComponent(query)}&limit=15`
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`HTTP error ${response.status}`)
  return response.json()
}

export async function submitProduct(formData: FormData): Promise<SubmissionResult> {
  const response = await fetch(`${API_BASE}/api/submit-product`, {
    method: 'POST',
    body: formData,  // multipart/form-data — do NOT set Content-Type manually
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP error ${response.status}`)
  }

  return response.json()
}
