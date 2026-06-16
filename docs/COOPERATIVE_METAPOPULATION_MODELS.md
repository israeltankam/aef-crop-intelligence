# Cooperative Metapopulation Disease Model

Date: 2026-06-12

## Scientific Rationale

Cooperative mode represents a landscape of small farmer plots inside one agricultural perimeter. Each plot is a local patch. Within each patch, AEF Crop Intelligence keeps the existing crop phenology, soil water, nutrient and disease models. Between plots, the cooperative mode adds a light metapopulation layer inspired by classical patch-occupancy and incidence-function thinking from Levins and Hanski.

This is appropriate for smallholder landscapes because disease pressure is not only local within one field. Vectors, rain splash, workers, tools and plant material can connect plots separated by paths, hedges or uncultivated strips.

## Local Patch Dynamics

For plot i, the existing single-field model gives local incidence:

$$
I_i^{local}(t)
$$

and local yield:

$$
Y_i^{local}(t)
$$

The phenological and physical model is unchanged.

## Distance Kernel Between Plots

Let d_ij be the distance between plot centroids. Connectivity from plot j to plot i is:

$$
K_{ij}=expleft(-rac{d_{ij}}{ell}ight), quad K_{ii}=0
$$

where ell is the cooperative dispersal scale. Rows are normalized so that a plot receives a bounded weighted pressure from other plots.

## External Infection Pressure

With plot area A_j, total active area A, insect/vector pressure V, and coupling coefficient beta_c:

$$
P_i^{meta}(t)=eta_c max(V,0.25) sum_{j 
e i} K_{ij},I_j(t)rac{A_j}{A}
$$

This keeps pressure higher when nearby infected plots are larger or more infectious.

## Coupled Incidence

The local and imported infection risks are combined as independent hazards:

$$
I_i(t)=1-left(1-I_i^{local}(t)ight)left(1-min(P_i^{meta}(t),0.35)ight)
$$

The cap avoids unrealistic instant saturation across the perimeter.

## Conservative Yield Adjustment

Imported metapopulation pressure adds only a conservative penalty:

$$
Delta I_i(t)=max(0,I_i(t)-I_i^{local}(t))
$$

$$
Y_i(t)=Y_i^{local}(t)left(1-0.25Delta I_i(t)ight)
$$

The detailed disease-yield loss remains controlled by the local disease model and disease CSV parameters.

## Cooperative Aggregation

For total active plot area A:

$$
ar{Y}(t)=sum_i Y_i(t)rac{A_i}{A}
$$

$$
I_{coop}(t)=sum_i I_i(t)rac{A_i}{A}
$$

$$
Production_{coop}(t)=sum_i Y_i(t)A_i
$$

## References For Review

- Levins, R. 1969. Some demographic and genetic consequences of environmental heterogeneity for biological control. Bulletin of the Entomological Society of America.
- Hanski, I. 1998. Metapopulation dynamics. Nature.
- Hanski, I. 1994. A practical model of metapopulation dynamics. Journal of Animal Ecology.
- Keeling, M. J. and Rohani, P. 2008. Modeling Infectious Diseases in Humans and Animals. Princeton University Press. The network/metapopulation epidemic framing is useful for patch-coupled disease systems.

## Pilot Validation Needs

- Estimate ell and beta_c by crop, disease type, vector presence and landscape connectivity.
- Compare modelled high-risk plots with field scouting observations.
- Separate vector-borne, rain-splash, soil-reservoir and windborne diseases with disease-specific coupling priors.
