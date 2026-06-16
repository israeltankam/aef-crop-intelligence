# src/models/fertilizer_service.py
import numpy as np
from src.models.fertilizer_optimizer import rank_fertilizer_products

class FertilizerService:
    def __init__(self):
        # Database based on the provided "Chunchao Products List"
        # Types: 'Balanced', 'Nitrogen', 'High_P', 'High_K', 'High_N', 'Operation'
        self.products = [
            # --- 0. OPERATIONS (New Phase 3) ---
            {'name': 'Canopy Pruning (Structural)', 'N': 0, 'P': 0, 'K': 0, 'type': 'Operation'},

            # --- 1. NPK Water Soluble Fertilizer ---
            {'name': 'NPK 20-20-20+TE (Soluble)', 'N': 20, 'P': 20, 'K': 20, 'type': 'Balanced'},
            {'name': 'NPK 19-19-19+TE (Soluble)', 'N': 19, 'P': 19, 'K': 19, 'type': 'Balanced'},
            {'name': 'NPK 18-18-18+TE (Soluble)', 'N': 18, 'P': 18, 'K': 18, 'type': 'Balanced'},
            {'name': 'NPK 30-10-10+TE (Soluble)', 'N': 30, 'P': 10, 'K': 10, 'type': 'High_N'},
            {'name': 'NPK 6-12-36+TE (Soluble)', 'N': 6, 'P': 12, 'K': 36, 'type': 'High_K'},
            {'name': 'NPK 8-12-24+TE (Soluble)', 'N': 8, 'P': 12, 'K': 24, 'type': 'High_K'},
            {'name': 'NPK 13-40-13 (Soluble)', 'N': 13, 'P': 40, 'K': 13, 'type': 'High_P'},
            {'name': 'NPK 15-15-30+TE (Soluble)', 'N': 15, 'P': 15, 'K': 30, 'type': 'High_K'},
            {'name': 'NPK 15-30-15+TE (Soluble)', 'N': 15, 'P': 30, 'K': 15, 'type': 'High_P'},
            {'name': 'NPK 6-10-16+TE (Soluble)', 'N': 6, 'P': 10, 'K': 16, 'type': 'High_K'},
            {'name': 'NPK 25-15-5 (Soluble)', 'N': 25, 'P': 15, 'K': 5, 'type': 'High_N'},
            {'name': 'NPK 10-10-30+TE (Soluble)', 'N': 10, 'P': 10, 'K': 30, 'type': 'High_K'},
            {'name': 'NPK 14-7-14+TE (Soluble)', 'N': 14, 'P': 7, 'K': 14, 'type': 'Balanced'}, 
            {'name': 'NPK 13-8-38+TE (Soluble)', 'N': 13, 'P': 8, 'K': 38, 'type': 'High_K'},
            {'name': 'NPK 20-10-10+TE (Soluble)', 'N': 20, 'P': 10, 'K': 10, 'type': 'High_N'},
            {'name': 'NPK 6-6-43+TE (Soluble)', 'N': 6, 'P': 6, 'K': 43, 'type': 'High_K'},
            {'name': 'NPK 13-45-10+TE (Soluble)', 'N': 13, 'P': 45, 'K': 10, 'type': 'High_P'},
            
            # --- 2. NPK Compound Fertilizer ---
            {'name': 'NPK 15-15-15 (Compound)', 'N': 15, 'P': 15, 'K': 15, 'type': 'Balanced'},
            {'name': 'NPK 12-12-17 (Compound)', 'N': 12, 'P': 12, 'K': 17, 'type': 'High_K'},
            {'name': 'NPK 24-7-8 (Compound)', 'N': 24, 'P': 7, 'K': 8, 'type': 'High_N'},
            {'name': 'NPK 15-20-5 (Compound)', 'N': 15, 'P': 20, 'K': 5, 'type': 'High_P'},
            {'name': 'NPK 22-4-22 (Compound)', 'N': 22, 'P': 4, 'K': 22, 'type': 'Balanced'}, 
            {'name': 'NPK 16-15-16 (Compound)', 'N': 16, 'P': 15, 'K': 16, 'type': 'Balanced'},
            {'name': 'NPK 20-5-10 (Compound)', 'N': 20, 'P': 5, 'K': 10, 'type': 'High_N'},
            {'name': 'NPK 20-8-15 (Compound)', 'N': 20, 'P': 8, 'K': 15, 'type': 'High_N'},
            {'name': 'NPK 20-15-10 (Compound)', 'N': 20, 'P': 15, 'K': 10, 'type': 'High_N'},
            {'name': 'NPK 20-20-0 (Compound)', 'N': 20, 'P': 20, 'K': 0, 'type': 'High_N'}, 
            {'name': 'NPK 16-20-0 (Compound)', 'N': 16, 'P': 20, 'K': 0, 'type': 'High_P'},
            {'name': 'NPK 22-16-0 (Compound)', 'N': 22, 'P': 16, 'K': 0, 'type': 'High_N'},
            {'name': 'NPK 26-18-0 (Compound)', 'N': 26, 'P': 18, 'K': 0, 'type': 'High_N'},
            {'name': 'NPK 30-0-5 (Compound)', 'N': 30, 'P': 0, 'K': 5, 'type': 'High_N'},
            {'name': 'NPK 15-0-15 (Compound)', 'N': 15, 'P': 0, 'K': 15, 'type': 'Balanced'},
            {'name': 'NPK 12-12-17+TE (Compound)', 'N': 12, 'P': 12, 'K': 17, 'type': 'High_K'},
            {'name': 'NPK 11-11-18+TE (Compound)', 'N': 11, 'P': 11, 'K': 18, 'type': 'High_K'},
            {'name': 'NPK 14-9-20+TE (Compound)', 'N': 14, 'P': 9, 'K': 20, 'type': 'High_K'},
            
            # --- 3. NPK Blended Fertilizer ---
            {'name': 'NPK 15-15-15 (Blended)', 'N': 15, 'P': 15, 'K': 15, 'type': 'Balanced'},
            {'name': 'NPK 16-16-16 (Blended)', 'N': 16, 'P': 16, 'K': 16, 'type': 'Balanced'},
            {'name': 'NPK 17-17-17 (Blended)', 'N': 17, 'P': 17, 'K': 17, 'type': 'Balanced'},
            {'name': 'NPK 19-19-19 (Blended)', 'N': 19, 'P': 19, 'K': 19, 'type': 'Balanced'},
            {'name': 'NPK 12-12-17 (Blended)', 'N': 12, 'P': 12, 'K': 17, 'type': 'High_K'},
            {'name': 'NPK 18-10-17 (Blended)', 'N': 18, 'P': 10, 'K': 17, 'type': 'Balanced'},
            {'name': 'NPK 20-25-5 (Blended)', 'N': 20, 'P': 25, 'K': 5, 'type': 'High_P'},
            {'name': 'NPK 12-10-18 (Blended)', 'N': 12, 'P': 10, 'K': 18, 'type': 'High_K'},
            {'name': 'NPK 20-5-10 (Blended)', 'N': 20, 'P': 5, 'K': 10, 'type': 'High_N'},
            {'name': 'NPK 16-10-22 (Blended)', 'N': 16, 'P': 10, 'K': 22, 'type': 'High_K'},
            {'name': 'NPK 20-15-10 (Blended)', 'N': 20, 'P': 15, 'K': 10, 'type': 'High_N'},
            {'name': 'NPK 20-20-0 (Blended)', 'N': 20, 'P': 20, 'K': 0, 'type': 'High_N'},
            {'name': 'NPK 22-16-0 (Blended)', 'N': 22, 'P': 16, 'K': 0, 'type': 'High_N'},
            {'name': 'NPK 30-0-5 (Blended)', 'N': 30, 'P': 0, 'K': 5, 'type': 'High_N'},
            {'name': 'NPK 12-12-18 (Blended)', 'N': 12, 'P': 12, 'K': 18, 'type': 'High_K'},
            {'name': 'NPK 11-11-17 (Blended)', 'N': 11, 'P': 11, 'K': 17, 'type': 'High_K'},
            {'name': 'NPK 10-10-10 (Blended)', 'N': 10, 'P': 10, 'K': 10, 'type': 'Balanced'},

            # --- 4. Nitrogen Fertilizer ---
            {'name': 'Ammonium Sulphate', 'N': 21, 'P': 0, 'K': 0, 'type': 'Nitrogen'},
            {'name': 'Nitrogen 26% Fertilizer', 'N': 26, 'P': 0, 'K': 0, 'type': 'Nitrogen'},
            {'name': 'Nitrogen 28% Fertilizer', 'N': 28, 'P': 0, 'K': 0, 'type': 'Nitrogen'},
            {'name': 'Nitrogen 34% Fertilizer', 'N': 34, 'P': 0, 'K': 0, 'type': 'Nitrogen'},
            
            # --- 5. Urea (Standard) ---
            {'name': 'Urea (Granular)', 'N': 46, 'P': 0, 'K': 0, 'type': 'Nitrogen'},
            
            # --- Other ---
            {'name': 'Humic Acid', 'N': 0, 'P': 0, 'K': 0, 'type': 'Other'} 
        ]

    def recommend_product(self, def_n, def_p, def_k):
        """
        Select the product whose N-P-K profile best matches the simulated deficit.

        The previous rule mostly selected the most concentrated product within a
        broad type.  The new rule ranks all non-operational products with a small
        vector score, then derives the dose from the limiting nutrient.  It stays
        lightweight while avoiding obviously unbalanced recommendations.
        """
        total_def = max(0.0, float(def_n or 0.0)) + max(0.0, float(def_p or 0.0)) + max(0.0, float(def_k or 0.0))
        if total_def < 1.0:
            return None, 0, ""

        ranked = rank_fertilizer_products(self.products, def_n, def_p, def_k)
        if not ranked:
            return None, 0, "No suitable fertilizer product matched the current deficit vector."

        choice = ranked[0]
        best_product = choice['product']
        amount = float(choice['amount_kg_ha'])
        match_pct = int(round(float(choice['match']) * 100.0))
        rationale = (
            f"Product profile matches the N-P-K deficit pattern at about {match_pct}%; "
            "dose is set by the limiting nutrient and should be checked against local availability."
        )
        return best_product['name'], round(amount, 1), rationale
