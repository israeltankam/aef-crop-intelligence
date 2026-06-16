# src/utils/coordinate_format.py
"""Human-friendly coordinate formatting and parsing helpers.

Farm users often recognise coordinates in degree-minute-second-cardinal form
(e.g. 9 deg 27 min 46 sec N, 14 deg 8 min 45 sec E) more easily than signed
decimal degrees.  The functions here keep the internal decimal representation
used by maps and Earth Engine, while displaying a field-ready DMS form.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple


def decimal_to_dms(value: float, is_latitude: bool = True) -> str:
    """Convert signed decimal degrees to DMS with a cardinal direction."""
    cardinal = "N" if is_latitude and value >= 0 else "S" if is_latitude else "E" if value >= 0 else "W"
    abs_value = abs(float(value))
    degrees = int(abs_value)
    minutes_float = (abs_value - degrees) * 60.0
    minutes = int(minutes_float)
    seconds = int(round((minutes_float - minutes) * 60.0))
    if seconds == 60:
        seconds = 0
        minutes += 1
    if minutes == 60:
        minutes = 0
        degrees += 1
    return f"{degrees}\u00b0 {minutes}\u2032 {seconds}\u2033 {cardinal}"


def format_latlon_dms(lat: float, lon: float) -> str:
    """Return a compact latitude/longitude DMS pair for display."""
    return f"{decimal_to_dms(lat, True)}    {decimal_to_dms(lon, False)}"


def _dms_to_decimal(degrees: float, minutes: float, seconds: float, cardinal: str) -> float:
    value = abs(float(degrees)) + abs(float(minutes)) / 60.0 + abs(float(seconds)) / 3600.0
    if cardinal.upper() in {"S", "W"}:
        value *= -1.0
    return value


def parse_coordinate_pair(text: str) -> Optional[Tuple[float, float]]:
    """Parse decimal or DMS coordinate pairs and return (lat, lon)."""
    if not text or not str(text).strip():
        return None
    s = str(text).strip()

    decimal_match = re.findall(r"[-+]?\d+(?:\.\d+)?", s)
    if len(decimal_match) >= 2 and not re.search(r"[NSEWnsew]", s):
        lat, lon = float(decimal_match[0]), float(decimal_match[1])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon

    pattern = re.compile(
        r"(\d+(?:\.\d+)?)\s*(?:\u00b0|deg|d)?\s*"
        r"(\d+(?:\.\d+)?)?\s*(?:\u2032|'|min|m)?\s*"
        r"(\d+(?:\.\d+)?)?\s*(?:\u2033|\"|sec|s)?\s*([NSEWnsew])"
    )
    parts = pattern.findall(s)
    if len(parts) >= 2:
        coords = []
        for deg, minute, second, card in parts[:2]:
            coords.append(_dms_to_decimal(float(deg), float(minute or 0), float(second or 0), card))
        lat = next((coords[i] for i, p in enumerate(parts[:2]) if p[3].upper() in {"N", "S"}), None)
        lon = next((coords[i] for i, p in enumerate(parts[:2]) if p[3].upper() in {"E", "W"}), None)
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    return None
