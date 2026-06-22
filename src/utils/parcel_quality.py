# src/utils/parcel_quality.py
"""Quality checks for cooperative parcel curation.

These helpers keep map editing ergonomic.  They do not reject user polygons;
instead they flag situations that usually indicate that candidate boundaries need
another look before running the agronomic engine.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional


def cooperative_parcel_quality(parcels: Iterable[Dict], perimeter_area_ha: Optional[float] = None) -> Dict[str, object]:
    """Summarise active parcel area, confidence and validation warnings."""
    active = [p for p in (parcels or []) if p.get('active', True)]
    areas = [max(0.0, float(p.get('area_ha', 0.0) or 0.0)) for p in active]
    confidences = [float(p.get('confidence', 1.0) or 0.0) for p in active]
    total_area = sum(areas)
    warnings: List[str] = []

    if not active:
        warnings.append('No active plot is selected.')
    if areas and min(areas) < 0.05:
        warnings.append('At least one plot is extremely small; verify whether it is a real field or a drawing artefact.')
    if areas and max(areas) > 8.0:
        warnings.append('At least one plot is large for a smallholder cooperative; verify that separate fields were not merged.')
    if confidences and sum(1 for c in confidences if c < 0.55) / len(confidences) > 0.35:
        warnings.append('Several plot boundaries have low automatic confidence and should be checked on the satellite map.')
    cultivated_fraction = 0.0
    unassigned_area_ha = 0.0
    large_gap_note = ''
    if perimeter_area_ha and perimeter_area_ha > 0:
        perimeter = float(perimeter_area_ha)
        cultivated_fraction = min(1.0, max(0.0, total_area / max(perimeter, 1e-6)))
        unassigned_area_ha = max(0.0, perimeter - total_area)
        if total_area > perimeter * 1.10:
            warnings.append('Active plot area exceeds the perimeter area by more than 10%; check overlapping or duplicated plots.')
        if active and cultivated_fraction < 0.65:
            large_gap_note = 'Large non-cultivated gaps inside the perimeter are allowed. Confirm that they are roads, fallows, water, buildings or uncultivated spaces rather than missed plots.'

    return {
        'active_count': len(active),
        'total_area_ha': total_area,
        'unassigned_area_ha': unassigned_area_ha,
        'cultivated_fraction': cultivated_fraction,
        'min_area_ha': min(areas) if areas else 0.0,
        'max_area_ha': max(areas) if areas else 0.0,
        'mean_confidence': sum(confidences) / len(confidences) if confidences else 0.0,
        'large_gap_note': large_gap_note,
        'warnings': warnings,
    }
