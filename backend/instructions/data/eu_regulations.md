# EU Regulatory Reference

## Overview

This document covers the key EU regulatory frameworks that govern the safety of food products and cosmetics sold in the European Union. Agents should use this as a reference when classifying ingredients, determining `eu_status`, and explaining safety concerns to consumers.

---

## EC No 1223/2009 — EU Cosmetics Regulation

**Full title:** Regulation (EC) No 1223/2009 of the European Parliament and of the Council on cosmetic products.

**Scope:** All cosmetic products placed on the EU market. A cosmetic is defined as any substance intended to be applied to the external body (skin, hair, nails, lips, external genitalia, teeth, mucous membranes) to clean, perfume, change appearance, protect, or maintain in good condition.

**Key Annexes:**

| Annex | Content |
|---|---|
| Annex II | List of **prohibited** substances (banned from all cosmetics) — ~1,600 entries |
| Annex III | List of **restricted** substances (allowed only under specified conditions, concentrations, or for specific product types) |
| Annex IV | Authorized **colorants** |
| Annex V | Authorized **preservatives** |
| Annex VI | Authorized **UV filters** |

**Implications for agents:**
- Any ingredient found in Annex II → `eu_status = 'banned'`, `safety_level = 'avoid'`, −30 pts penalty, score floor to D.
- Any ingredient found in Annex III → `eu_status = 'restricted'`. Severity depends on the restriction (some are minor, some are near-bans).
- Ingredients not listed in any Annex and not used as a colorant, preservative, or UV filter are generally permitted unless prohibited by other regulation.

---

## Regulation (EC) No 1333/2008 — EU Food Additives

**Full title:** Regulation (EC) No 1333/2008 of the European Parliament and of the Council on food additives.

**Scope:** All food additives used in food products placed on the EU market. A food additive is any substance not normally consumed as food but added intentionally to food for technological purposes.

**Key principles:**
- Only additives listed in the EU permitted list may be used.
- Each additive is authorized for specific food categories at specific maximum levels.
- All additives must be declared in the ingredient list by name or E-number.

**E-number ranges:**

| Range | Category |
|---|---|
| E100–E199 | Colours |
| E200–E299 | Preservatives |
| E300–E399 | Antioxidants, acidity regulators |
| E400–E499 | Emulsifiers, thickeners, stabilizers, gelling agents |
| E500–E599 | Acidity regulators, anti-caking agents |
| E600–E699 | Flavour enhancers |
| E700–E799 | Antibiotics (feed additives, rarely in human food) |
| E900–E999 | Glazing agents, gases, sweeteners |
| E1000–E1599 | Additional chemicals |

**Re-evaluation programme:** Under Regulation (EU) 257/2010, EFSA is systematically re-evaluating all previously authorized food additives. Some may be restricted or removed as re-evaluations conclude.

---

## REACH Regulation — EC No 1907/2006

**Full title:** Regulation (EC) No 1907/2006 concerning the Registration, Evaluation, Authorisation and Restriction of Chemicals (REACH).

**Scope:** Industrial chemicals and substances used in manufacturing, including cosmetic ingredients. Managed by ECHA (European Chemicals Agency).

**Key lists for agents:**

- **SVHC (Substances of Very High Concern)**: Substances with serious and often irreversible effects on health or the environment. Includes carcinogens, mutagens, reproductive toxins (CMR), persistent bioaccumulative toxins (PBT), endocrine disruptors.
  - Candidate List: substances being evaluated for Authorization Requirement
  - Authorization List (Annex XIV): substances requiring specific authorization to use
  - Restriction List (Annex XVII): substances with restrictions on use/manufacturing/placing on market

**Implications for agents:** An ingredient on the SVHC Candidate List or REACH Annex XIV/XVII should have `eu_status = 'restricted'` or `'banned'` depending on specifics, and `concerns` should include the relevant category.

---

## Commonly Flagged Cosmetic Ingredients

### Banned in EU (Annex II of EC 1223/2009)

| Ingredient | Concern | Notes |
|---|---|---|
| Dibutyl phthalate (DBP) | Endocrine disruptor, reproductive toxin | Banned EU cosmetics |
| Diethylhexyl phthalate (DEHP) | Endocrine disruptor, reproductive toxin | Banned EU cosmetics |
| Benzyl butyl phthalate (BBP) | Endocrine disruptor | Banned EU cosmetics |
| Triclosan | Endocrine disruptor, antimicrobial resistance | Banned EU rinse-off cosmetics; restricted in others |
| Lead and lead compounds | Neurotoxin, carcinogen | Banned (trace contamination threshold only) |
| Mercury and mercury compounds | Neurotoxin | Banned |
| Formaldehyde | Carcinogen (IARC Group 1) | Banned above 0.2% in leave-on; banned above 0.1% in oral care |
| Coal tar dyes (many CI numbers) | Carcinogen | Many specific CI numbers banned |

### Restricted in EU (Annex III of EC 1223/2009)

| Ingredient | Restriction | Concern |
|---|---|---|
| Methylisothiazolinone (MIT) | Banned in leave-on cosmetics; max 0.0015% in rinse-off | Skin sensitizer, allergen |
| Methylchloroisothiazolinone (CMIT) | Max 0.0015% (in combination with MIT) in rinse-off only | Skin sensitizer |
| Resorcinol | Max 0.5% in hair colorants | Endocrine disruptor |
| Hydroquinone | Max 0.3% in nail products; banned in other cosmetics | Carcinogen (Group 2B) |
| Benzophenone-3 (Oxybenzone) | Max 6% with warning label | Endocrine disruptor |
| Salicylic acid | Max 2% in rinse-off, 0.5% in body lotion | Not for children under 3 |
| Propylparaben | Max 0.14% (alone) or 0.19% combined parabens | Endocrine disruptor |
| Butylparaben | Max 0.14% (alone) or 0.19% combined parabens | Endocrine disruptor |

### Commonly Flagged (Not Banned, but Notable)

| Ingredient | Concern | `safety_level` |
|---|---|---|
| Sodium Lauryl Sulfate (SLS) | Skin irritant, strips natural oils | `caution` |
| Sodium Laureth Sulfate (SLES) | May contain 1,4-dioxane traces; irritant | `caution` |
| Methylparaben | Paraben; weak endocrine disruption | `caution` |
| Ethylparaben | Paraben | `caution` |
| BHA (Butylated Hydroxyanisole) | Endocrine disruptor, IARC 2B carcinogen | `avoid` |
| BHT (Butylated Hydroxytoluene) | Possible endocrine disruption | `caution` |
| DMDM Hydantoin | Formaldehyde releaser | `avoid` |
| Imidazolidinyl urea | Formaldehyde releaser | `avoid` |
| Quaternium-15 | Formaldehyde releaser | `avoid` |
| Diazolidinyl urea | Formaldehyde releaser | `avoid` |
| Parfum / Fragrance | Undisclosed blend; potential allergens | `caution` |
| Alcohol Denat | Skin-drying; irritant at high concentrations | `caution` |
| Polyethylene Glycols (PEGs) | May contain contaminants (ethylene oxide, 1,4-dioxane) | `caution` |

---

## Food Additives with Concerns

### E-Numbers — Avoid Classification

| E-Number | Name | Concern |
|---|---|---|
| E102 | Tartrazine (Yellow 5) | Linked to hyperactivity in children; banned in some countries |
| E104 | Quinoline Yellow | Hyperactivity; banned in US |
| E110 | Sunset Yellow FCF | Hyperactivity; possible allergen |
| E122 | Carmoisine | Hyperactivity |
| E123 | Amaranth | Banned in US; EFSA under review |
| E124 | Ponceau 4R | Hyperactivity |
| E127 | Erythrosine | Thyroid disruption; banned in US |
| E129 | Allura Red AC | Hyperactivity; Southampton Six |
| E211 | Sodium Benzoate | Forms benzene with Vitamin C; hyperactivity |
| E220 | Sulphur dioxide | Allergen (sulphites); triggers asthma |
| E249 | Potassium nitrite | Nitrosamines formation; carcinogen |
| E250 | Sodium nitrite | Nitrosamines formation; carcinogen |
| E951 | Aspartame | Controversial; IARC 2B carcinogen (2023); ADI-based approval |
| E954 | Saccharin | Bladder cancer in animals; IARC 2B |
| E621 | Monosodium Glutamate (MSG) | Controversy; generally regarded as safe at normal levels |

### E-Numbers — Caution Classification

| E-Number | Name | Concern |
|---|---|---|
| E150d | Caramel IV (ammonia-sulphite process) | Contains 4-MEI, a possible carcinogen |
| E171 | Titanium dioxide | Nanoparticle form banned in EU food since 2022; under review |
| E320 | BHA | Endocrine disruptor, IARC 2B |
| E321 | BHT | Possible endocrine disruptor |
| E407 | Carrageenan | Degraded form linked to inflammation; food-grade generally considered safe |
| E450–E452 | Phosphates | High intake linked to kidney disease; ubiquitous in processed food |
| E471 | Mono- and diglycerides | Often derived from palm oil; EFSA under review |
| E635 | Disodium 5'-ribonucleotides | Allergen trigger |

---

## EU Food Allergen Declaration Requirements

Under EU Regulation No 1169/2011 on food information to consumers, 14 allergen groups must be declared in the ingredient list in a way that distinguishes them from other ingredients (e.g., bold, italics, contrasting color):

| # | Allergen | Common Sources |
|---|---|---|
| 1 | Cereals containing gluten | Wheat, rye, barley, oats, spelt, kamut |
| 2 | Crustaceans | Shrimp, crab, lobster |
| 3 | Eggs | All egg-derived products |
| 4 | Fish | All fish species |
| 5 | Peanuts | Groundnuts |
| 6 | Soybeans | Tofu, miso, soy lecithin |
| 7 | Milk | Lactose, whey, casein, butter |
| 8 | Tree nuts | Almonds, hazelnuts, walnuts, cashews, pecans, Brazil nuts, pistachios, macadamia, Queensland nut |
| 9 | Celery | Celery root, celeriac |
| 10 | Mustard | Mustard seeds, mustard oil |
| 11 | Sesame seeds | Tahini, sesame oil |
| 12 | Sulphur dioxide and sulphites | >10 mg/kg or 10 mg/L — wines, dried fruits |
| 13 | Lupin | Lupin flour, seeds |
| 14 | Molluscs | Oysters, mussels, clams, squid |

**Agent rule:** When any of these 14 allergen groups is detected in an ingredient list (whether declared in bold on the label or matched through ingredient name analysis), set `is_allergen = true` on the relevant `product_ingredients` row and apply the −3 pt allergen penalty per occurrence.
