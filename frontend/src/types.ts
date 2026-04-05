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

export interface SubmissionResult {
  submission_id:      number | null
  product:            ExtractedProduct
  ingredients:        ParsedIngredient[]
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
  id:           number
  barcode:      string | null
  status:       'pending' | 'analyzing' | 'complete' | 'failed'
  product_name: string | null
  brand:        string | null
  submitted_at: string | null  // maps to created_at in DB
  analyzed_at:  string | null
  error:        string | null
  report:       SafetyReport | null
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
  grade: 'A' | 'B' | 'C' | 'D' | 'E'
  summary: string
  ingredients_analysis: IngredientAnalysis[]
  positive_points: string[]
  negative_points: string[]
  not_found: boolean
  recalls: RecallAlert[]
}
