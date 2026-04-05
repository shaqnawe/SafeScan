import type { SafetyReport, SubmissionResult, UserSubmission } from './types'

// Use VITE_API_URL env var so the app works on other devices on the same network.
// In .env.local set: VITE_API_URL=http://192.168.x.x:8000
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8000'

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
