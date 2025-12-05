# src/models/evapotranspiration.py
import math
import numpy as np

def _saturation_vapor_pressure(t_c):
    return 0.6108 * math.exp((17.27 * t_c) / (t_c + 237.3))

def _delta_svp(t_c):
    es = _saturation_vapor_pressure(t_c)
    return 4098.0 * es / ((t_c + 237.3) ** 2)

def _psychrometric_constant(elevation_m):
    P = 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26
    return 0.000665 * P

def _extraterrestrial_radiation(doy, lat_rad):
    dr = 1.0 + 0.033 * math.cos(2.0 * math.pi / 365.0 * doy)
    solar_decl = 0.409 * math.sin(2.0 * math.pi / 365.0 * doy - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(lat_rad) * math.tan(solar_decl))))
    Gsc = 0.0820
    Ra = (24.0 * 60.0 / math.pi) * Gsc * dr * (
        ws * math.sin(lat_rad) * math.sin(solar_decl) + math.cos(lat_rad) * math.cos(solar_decl) * math.sin(ws)
    )
    return Ra

def penman_monteith_et0(tmax_c, tmin_c, tmean_c=None, rs=None, uz=2.0, rh_mean=None, doy=None, lat_deg=None, elevation_m=0.0):
    """
    Computes FAO-56 PM ET0 (mm/day).
    Assumes Rs is in MJ/m2/day.
    """
    if tmean_c is None: tmean_c = 0.5 * (tmax_c + tmin_c)
    delta = _delta_svp(tmean_c)
    es_tmax = _saturation_vapor_pressure(tmax_c)
    es_tmin = _saturation_vapor_pressure(tmin_c)
    es = 0.5 * (es_tmax + es_tmin)
    
    if rh_mean is not None:
        ea = (rh_mean / 100.0) * es
    else:
        ea = _saturation_vapor_pressure(tmin_c)
    
    gamma = _psychrometric_constant(elevation_m)
    
    if rs is None:
        # Fallback if radiation is missing (shouldn't happen with your weather service)
        return 0.0023 * (tmean_c + 17.8) * ((tmax_c - tmin_c) ** 0.5) * 0.408

    # Net shortwave
    albedo = 0.23
    Rns = (1.0 - albedo) * rs

    # Net longwave
    if doy is None: doy = 180
    if lat_deg is None: lat_deg = 0.0
    
    lat_rad = math.radians(lat_deg)
    Ra = _extraterrestrial_radiation(doy, lat_rad)
    Rso = (0.75 + (2e-5 * elevation_m)) * Ra
    
    # Avoid div by zero
    Rs_Rso = rs / Rso if Rso > 0.0 else 0.7
    Rs_Rso = max(0.3, min(Rs_Rso, 1.0))
    
    sigma = 4.903e-9
    tmax_k = tmax_c + 273.16
    tmin_k = tmin_c + 273.16
    Rnl = sigma * 0.5 * (tmax_k ** 4 + tmin_k ** 4) * (0.34 - 0.14 * math.sqrt(max(0.0, ea))) * (1.35 * Rs_Rso - 0.35)
    
    Rn = Rns - Rnl
    G = 0.0 # Daily soil heat flux approx 0
    
    numerator = 0.408 * delta * (Rn - G) + gamma * (900.0 / (tmean_c + 273.0)) * uz * (es - ea)
    denominator = delta + gamma * (1.0 + 0.34 * uz)
    
    et0 = numerator / denominator
    return float(np.clip(et0, 0.5, 15.0)) # Clip to realistic bounds