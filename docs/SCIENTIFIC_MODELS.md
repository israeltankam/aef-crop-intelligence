# AEF Crop Intelligence - Scientific Model Specification

Date: 2026-06-10
Status: review draft before pilot validation

This document records the models introduced by the scientific refactor. It is intentionally explicit so agronomists can review assumptions before field deployment.

## 1. Model Selection Layer

The application now separates model selection from model execution. The selector chooses the scientifically preferred family from crop type, objective and data quality:

| Context | Preferred model family | Current implementation status |
|---|---|---|
| Irrigation / water-limited analysis | AquaCrop + CROPWAT | Selected as target; AEF-lite remains fallback until adapter is installed |
| Annual staple crops | DSSAT / APSIM | Selected as target; AEF-lite remains fallback until adapter is installed |
| Perennial crops | STICS / APSIM perennial pathway | Selected as target; AEF-lite remains fallback until adapter is installed |
| Unknown or unsupported crop | AEF-lite fallback | Operational fallback only |

The selector emits a confidence score:

\[
C = C_0 \times Q_{soil}
\]

where \(C_0\) is the confidence assigned to the model family and \(Q_{soil}=0.92\) for manually entered soil data or \(0.76\) for automatically detected soil data.

## 2. Spatial Disease Tau-Leaping Model

The disease grid has internal latent, infectious, resolved and reservoir states:

\[
S_{i,t} = 1 - E_{i,t} - I_{i,t} - R_{i,t}
\]

\[
\lambda^E_{i,t} = \beta_m \cdot D_t \cdot F_t \cdot P_{i,t} \cdot S_{i,t}
\]

where:

- \(\beta_m\) is the disease-family infection parameter corrected by crop resistance;
- \(D_t\) is the spread driver from wind, rain and vector pressure;
- \(F_t\) is environmental favorability from temperature, humidity and rain;
- \(P_{i,t}\) is local infectious pressure from convolution of infectious cells and residual inoculum.

For deterministic dashboard runs:

\[
\Delta E_{i,t} = \lambda^E_{i,t}
\]

For ensemble dossier runs, tau-leaping is used:

\[
\Delta E_{i,t} = \frac{\text{Poisson}(N_v \lambda^E_{i,t})}{N_v}
\]

with virtual cell population \(N_v=120\). This keeps proportions smooth while preserving stochastic variability.

Latent activation:

\[
\Delta I_{i,t} = \frac{E_{i,t}}{L_m}
\]

Recovery/resolution:

\[
\Delta R_{i,t} = I_{i,t} \cdot \left(\rho_m + \rho_{control}\right) \cdot \left(1 + 2(1-F_t)\right)
\]

Residual inoculum:

\[
Z_{i,t+1}=Z_{i,t}(1-d_m c_z)+r_m\Delta R_{i,t}+s_m I_{i,t}F_t
\]

Long-distance jumps are sampled from a non-local tau-leaping pressure:

\[
\Lambda^{jump}_t = j_m c_j \max(F_t,0.05) \max(P^{insect}_t,0.25)
\left(\sum_i I_{i,t}+0.45 N^I_t\right)
\]

\[
J_t \sim \text{Poisson}(\Lambda^{jump}_t)
\]

where \(N^I_t\) is the number of infectious grid cells above the operational threshold. In deterministic mode, jumps are triggered when \(\Lambda^{jump}_t\) exceeds the disease-family floor. Jump destinations are sampled among susceptible cells, with a small distance bonus so secondary foci may appear away from the initial focus. This avoids unrealistic concentric-only fronts, especially for vector-borne diseases.

## 3. Disease Families

| Family | Typical use | Key assumptions |
|---|---|---|
| vector-borne chronic | viral diseases with whitefly/leafhopper/aphid/mealybug vectors | infected plants are persistent reservoirs; natural recovery is weak |
| fungal airborne | foliar/canopy fungal diseases | humidity, wind, rain and residual inoculum control spread |
| bacterial splash | bacterial diseases moved by rain/splash | local rain spread plus occasional jumps |
| soil reservoir | soil/root/residue diseases | persistent reservoir, slower spatial spread |

CSV parameters remain essential. The disease database should be extended with disease-specific latency, reservoir persistence, intervention efficacy, and validated host/pathogen references.

## 4. Counterfactual Interventions

The app does not assume interventions already happened. It compares:

1. Do nothing.
2. Minimum useful action.
3. Intermediate strategy.
4. Optimized recommendation.

For roguing:

\[
Y' = Y \cdot (1 - L_{rogue}) \cdot \left[(1-I) + I \cdot y_{retained}\right]
\]

where \(L_{rogue}\) is the productive-plant loss caused by plant removal. This explicitly balances inoculum reduction against yield loss.

## 5. Adaptive Calibration

The current operational app keeps a light calibration path. The research target is a Bayesian state-space model:

\[
\mathbf{x}_{t+1}=f(\mathbf{x}_t,\theta,u_t,w_t)
\]

\[
\mathbf{y}_t=g(\mathbf{x}_t,\theta)+v_t
\]

where \(\mathbf{x}_t\) includes biomass, soil water, N/P/K, latent disease, infectious disease and reservoir pressure. Observations may be yield, biomass, soil nutrients, disease incidence or satellite vegetation indicators.

The current light active-learning rule recommends the next measurement around the largest disease acceleration or largest nutrient stress. The pilot target is PMMH / Particle Gibbs for deeper calibration when enough field data exist.

## 6. Remote Sensing Disease Detection

The automatic satellite module must remain probabilistic. It should output:

- probability of biotic stress;
- probability of abiotic stress;
- top disease candidates compatible with crop, region, season, weather and spectral signature;
- a one-click validation path for the user.

The current refactor preserves the module but prepares downstream disease modelling to accept uncertain disease identity. Future work should add light classifiers using Sentinel-2 NDVI/NDRE/red-edge/NDMI features and confusion-aware outputs.


## 7. Reality Check and Forecast Uncertainty

Satellite reality checks are valid only on dates where real observations can exist. The comparison window is therefore:

\[
T_{obs}=\{t: \max(t_{planting},t_{sim,0}) \le t \le \min(t_{today},t_{sim,end},t_{sat,last})\}
\]

The application compares modelled LAI with observed Sentinel-2 NDVI only on \(T_{obs}\). Dates after today, and dates after the latest available cloud-free satellite observation, are forecasts and are not displayed as reality-check evidence.

The dossier and dashboard expose margins of error from stochastic ensemble runs:

\[
\bar{y}_t = \frac{1}{M}\sum_{m=1}^M y^{(m)}_t, \quad
s_t = \sqrt{\frac{1}{M-1}\sum_{m=1}^M (y^{(m)}_t-\bar{y}_t)^2}
\]

\[
CI_{95,t} \approx \bar{y}_t \pm 1.96s_t
\]

The same rule is used for forecast yield, total production and final disease incidence. These intervals are not a full Bayesian posterior yet; they are an operational uncertainty envelope until the adaptive calibration module is upgraded to particle filtering / PMMH.

For automatic disease detection, the satellite anomaly observation date and the management detection date are deliberately separated:

\[
t_{sat}=\text{latest significant satellite anomaly date}, \quad t_{detect}=t_{today}
\]

The satellite date remains useful for traceability, while future intervention scenarios start from the day the user actually runs the diagnosis.
