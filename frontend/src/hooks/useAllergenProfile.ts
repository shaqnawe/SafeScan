import { useState, useCallback } from 'react'

const STORAGE_KEY = 'safescan_allergens'

export interface AllergenInfo {
  id:      string
  label:   string
  emoji:   string
  // keywords to match against raw ingredient text (lowercase)
  keywords: string[]
}

export const ALL_ALLERGENS: AllergenInfo[] = [
  {
    id: 'gluten',
    label: 'Gluten',
    emoji: '🌾',
    keywords: ['wheat', 'gluten', 'barley', 'rye', 'oat', 'spelt', 'kamut', 'farro', 'durum', 'semolina', 'bulgur', 'triticale'],
  },
  {
    id: 'dairy',
    label: 'Dairy',
    emoji: '🥛',
    keywords: ['milk', 'dairy', 'lactose', 'whey', 'casein', 'butter', 'cream', 'cheese', 'yogurt', 'lacto', 'skimmed milk', 'whole milk'],
  },
  {
    id: 'eggs',
    label: 'Eggs',
    emoji: '🥚',
    keywords: ['egg', 'albumin', 'ovalbumin', 'lysozyme', 'mayonnaise'],
  },
  {
    id: 'peanuts',
    label: 'Peanuts',
    emoji: '🥜',
    keywords: ['peanut', 'groundnut', 'arachis'],
  },
  {
    id: 'soy',
    label: 'Soy',
    emoji: '🫘',
    keywords: ['soy', 'soya', 'tofu', 'edamame', 'miso', 'tempeh', 'soybean'],
  },
  {
    id: 'tree_nuts',
    label: 'Tree Nuts',
    emoji: '🌰',
    keywords: ['almond', 'hazelnut', 'walnut', 'cashew', 'pecan', 'pistachio', 'macadamia', 'brazil nut', 'pine nut', 'chestnut', 'coconut'],
  },
  {
    id: 'fish',
    label: 'Fish',
    emoji: '🐟',
    keywords: ['fish', 'cod', 'salmon', 'tuna', 'anchovy', 'sardine', 'herring', 'tilapia', 'bass', 'flounder', 'halibut', 'mackerel'],
  },
  {
    id: 'shellfish',
    label: 'Shellfish',
    emoji: '🦐',
    keywords: ['crustacean', 'shellfish', 'shrimp', 'prawn', 'crab', 'lobster', 'crayfish', 'barnacle'],
  },
  {
    id: 'sesame',
    label: 'Sesame',
    emoji: '🌿',
    keywords: ['sesame', 'tahini', 'gingelly', 'til'],
  },
  {
    id: 'mustard',
    label: 'Mustard',
    emoji: '🟡',
    keywords: ['mustard'],
  },
  {
    id: 'celery',
    label: 'Celery',
    emoji: '🥬',
    keywords: ['celery', 'celeriac'],
  },
  {
    id: 'sulphites',
    label: 'Sulphites',
    emoji: '🍷',
    keywords: ['sulphite', 'sulfite', 'sulphur dioxide', 'sulfur dioxide', 'e220', 'e221', 'e222', 'e223', 'e224', 'e225', 'e226', 'e227', 'e228'],
  },
  {
    id: 'lupin',
    label: 'Lupin',
    emoji: '🌼',
    keywords: ['lupin', 'lupine'],
  },
  {
    id: 'molluscs',
    label: 'Molluscs',
    emoji: '🦪',
    keywords: ['mollusc', 'mollusk', 'squid', 'octopus', 'clam', 'oyster', 'mussel', 'scallop', 'abalone'],
  },
]

function load(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function save(ids: string[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
  } catch {}
}

export function useAllergenProfile() {
  const [activeIds, setActiveIds] = useState<string[]>(load)

  const toggleAllergen = useCallback((id: string) => {
    setActiveIds(prev => {
      const next = prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]
      save(next)
      return next
    })
  }, [])

  const clearAll = useCallback(() => {
    save([])
    setActiveIds([])
  }, [])

  const activeAllergens = ALL_ALLERGENS.filter(a => activeIds.includes(a.id))

  return { activeIds, activeAllergens, toggleAllergen, clearAll }
}

/** Check which active allergens appear in a list of ingredient name strings. */
export function matchAllergens(
  ingredientNames: string[],
  activeAllergens: AllergenInfo[],
): Map<string, string[]> {
  // Returns: allergen_id → list of matching ingredient names
  const result = new Map<string, string[]>()
  const lowerNames = ingredientNames.map(n => n.toLowerCase())

  for (const allergen of activeAllergens) {
    const matches: string[] = []
    for (let i = 0; i < lowerNames.length; i++) {
      const name = lowerNames[i]
      if (allergen.keywords.some(kw => name.includes(kw))) {
        matches.push(ingredientNames[i])
      }
    }
    if (matches.length > 0) {
      result.set(allergen.id, matches)
    }
  }

  return result
}
