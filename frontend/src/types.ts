export interface ExtractedProduct {
  brand:          string | null
  product_name:   string | null
  barcode:        string | null
  product_type:   string
  certifications: string[]
  confidence:     number
  notes:          string | null
}

export interface ParsedIngredient {
  name:               string
  position:           number
  is_allergen:        boolean
  is_fragrance_blend: boolean
  concerns:           string[]
}

export type CallStatus = 'ok' | 'failed' | 'not_attempted'

export interface SubmissionResult {
  submission_id:      number | null
  product:            ExtractedProduct
  product_status:     CallStatus
  ingredients:        ParsedIngredient[]
  ingredients_status: CallStatus
  parsing_confidence: number
  parsing_notes:      string | null
  ready_for_analysis: boolean
}

export interface IngredientAnalysis {
  name: string
  safety_level: 'safe' | 'caution' | 'avoid'
  concern?: string | null
}

export interface UserSubmission {
  id:                 number
  barcode:            string | null
  status:             'pending' | 'analyzing' | 'complete' | 'failed'
  product_name:       string | null
  brand:              string | null
  submitted_at:       string | null  // maps to created_at in DB
  analyzed_at:        string | null
  error:              string | null
  report:             SafetyReport | null
  // Per-call extraction outcomes from the image agent (orthogonal to `status`)
  product_status:     CallStatus
  ingredients_status: CallStatus
}

export interface RecallAlert {
  title: string
  description?: string | null
  risk_level?: string | null   // 'serious' | 'high' | 'medium' | 'low'
  category?: string | null
  link?: string | null
  published_at?: string | null
}

export interface SafetyReport {
  product_name: string
  brand: string
  product_type: string
  barcode: string
  image_url?: string | null
  score: number
  grade: 'A' | 'B' | 'C' | 'D'
  summary: string
  ingredients_analysis: IngredientAnalysis[]
  positive_points: string[]
  negative_points: string[]
  not_found: boolean
  recalls: RecallAlert[]
}
