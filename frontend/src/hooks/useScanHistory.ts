import { useState, useCallback } from 'react'
import type { SafetyReport } from '../types'

const STORAGE_KEY = 'safescan_history'
const MAX_ENTRIES = 20

export interface ScanHistoryEntry {
  barcode: string
  name: string
  brand: string
  grade: string
  score: number
  product_type: string
  image_url: string | null
  scanned_at: string // ISO timestamp
}

function loadHistory(): ScanHistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveHistory(entries: ScanHistoryEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export function useScanHistory() {
  const [history, setHistory] = useState<ScanHistoryEntry[]>(loadHistory)

  const addEntry = useCallback((report: SafetyReport) => {
    if (report.not_found) return

    const entry: ScanHistoryEntry = {
      barcode:     report.barcode,
      name:        report.product_name || 'Unknown Product',
      brand:       report.brand || '',
      grade:       report.grade,
      score:       report.score,
      product_type: report.product_type,
      image_url:   report.image_url ?? null,
      scanned_at:  new Date().toISOString(),
    }

    setHistory(prev => {
      // Remove any existing entry for the same barcode, then prepend new one
      const filtered = prev.filter(e => e.barcode !== report.barcode)
      const updated = [entry, ...filtered].slice(0, MAX_ENTRIES)
      saveHistory(updated)
      return updated
    })
  }, [])

  const clearHistory = useCallback(() => {
    saveHistory([])
    setHistory([])
  }, [])

  return { history, addEntry, clearHistory }
}
