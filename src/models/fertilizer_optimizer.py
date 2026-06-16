# src/models/fertilizer_optimizer.py
"""Lightweight fertilizer product scoring helpers.

The optimizer deliberately remains simple: AEF often runs on small deployments
where loading a large mixed-integer optimizer would slow the app.  We therefore
score available products against the N-P-K deficit vector using cosine similarity
(profile match) and nutrient coverage (how much product is required to cover the
limiting nutrient).  This is more agronomically transparent than selecting only
the highest-analysis fertilizer.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Tuple


def _positive_vector(n: float, p: float, k: float) -> Tuple[float, float, float]:
    return (max(0.0, float(n or 0.0)), max(0.0, float(p or 0.0)), max(0.0, float(k or 0.0)))


def cosine_match(deficits: Tuple[float, float, float], product: Dict[str, float]) -> float:
    """Return 0-1 nutrient profile similarity between deficit and product."""
    d = _positive_vector(*deficits)
    p = _positive_vector(product.get('N', 0.0), product.get('P', 0.0), product.get('K', 0.0))
    d_norm = math.sqrt(sum(v * v for v in d))
    p_norm = math.sqrt(sum(v * v for v in p))
    if d_norm <= 0.0 or p_norm <= 0.0:
        return 0.0
    return max(0.0, min(1.0, sum(a * b for a, b in zip(d, p)) / (d_norm * p_norm)))


def required_amount_kg_ha(deficits: Tuple[float, float, float], product: Dict[str, float]) -> float:
    """Estimate kg/ha product needed to address the limiting positive nutrient."""
    requirements: List[float] = []
    for deficit, nutrient in zip(_positive_vector(*deficits), ['N', 'P', 'K']):
        content = max(0.0, float(product.get(nutrient, 0.0) or 0.0))
        if deficit > 0.0 and content > 0.0:
            requirements.append(deficit / (content / 100.0))
    return max(requirements) if requirements else 0.0


def rank_fertilizer_products(products: Iterable[Dict[str, float]], def_n: float, def_p: float, def_k: float) -> List[Dict[str, object]]:
    """Rank products by nutrient profile fit, dose practicality and completeness."""
    deficits = _positive_vector(def_n, def_p, def_k)
    ranked: List[Dict[str, object]] = []
    for product in products:
        if product.get('type') == 'Operation':
            continue
        match = cosine_match(deficits, product)
        amount = required_amount_kg_ha(deficits, product)
        if match <= 0.0 or amount <= 0.0:
            continue

        # Penalise impractically high application rates while keeping the score
        # continuous.  The value is a soft agronomic guardrail, not a regulation.
        dose_penalty = max(0.45, min(1.0, 600.0 / max(600.0, amount)))
        covered = sum(1 for deficit, nutrient in zip(deficits, ['N', 'P', 'K']) if deficit <= 0.0 or float(product.get(nutrient, 0.0) or 0.0) > 0.0)
        completeness = covered / 3.0
        score = 0.72 * match + 0.18 * dose_penalty + 0.10 * completeness
        ranked.append({'product': product, 'amount_kg_ha': amount, 'match': match, 'score': score})
    return sorted(ranked, key=lambda row: row['score'], reverse=True)
