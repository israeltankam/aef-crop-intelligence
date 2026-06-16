# Rapport detaille - AEF Crop Intelligence

Version du rapport : 2026-06-11
Copie corrigee : `/mnt/c/Users/tankamch/AppData/Local/Temp/aef_corrected_1781125311822`
Tests cibles : 50/50 reussis

Ce document est structure en 50 pages Markdown. Les balises de saut de page facilitent une conversion PDF ou Word si necessaire.

## Page 01 - Synthese executive

Ce rapport documente l'audit, les corrections et la validation de la copie corrigee d'AEF Crop Intelligence. Le travail couvre la logique de generation du champ, la detection automatique des sols, la detection satellite des maladies, les modeles de maladie et de croissance, la calibration adaptative, les CSV cultures/maladies, l'internationalisation, les spinners, le rollback, les dependances et le contact d'acces.

La correction a ete realisee dans la copie de travail accessible a Codex : `/mnt/c/Users/tankamch/AppData/Local/Temp/aef_corrected_1781125311822`. Le dossier WSL original `/home/tankamch/projects/AEF/app` est reste inaccessible en ecriture et meme en lecture effective depuis les outils disponibles, avec erreurs `EPERM` et impossibilite de lancer le shell. Aucun changement direct n'a donc ete applique au dossier WSL original pendant cette session.

La derniere passe de validation ciblee comporte 50 tests : 50 reussis, 0 echoue. La passe precedente de coherence statique comportait 1000 controles : 1000 reussis, 0 echoue.

<div style="page-break-after: always;"></div>

## Page 02 - Perimetre du travail

Le perimetre couvre cinq familles d'evolutions. D'abord, le smart field : generation d'un champ a partir d'un centre GPS ou d'une recherche de lieu, sans imposer une forme carree. Ensuite, la detection des sols : audit de l'approche OpenLandMap existante et amelioration uniquement quand cela apporte un gain net. Troisiemement, les fondations scientifiques deja introduites : modeles maladie tau-leaping, selection de modeles de croissance, triage satellite, calibration adaptative et comparaison de scenarios. Quatriemement, les donnees CSV : varietes, cultures, maladies et parametres. Enfin, la qualite operationnelle : backups, journal de modifications, rollback, tests, requirements et documentation.

Le principe directeur est la prudence scientifique : l'application doit etre utile aux utilisateurs non experts, mais ne doit pas presenter une estimation automatique comme une mesure terrain certaine. Les sorties automatiques sont donc accompagnees de niveaux de confiance, de notes de validation et de possibilites d'edition.

<div style="page-break-after: always;"></div>

## Page 03 - Contrainte environnementale

Les outils Codex de cette session n'ont pas pu acceder directement au workspace WSL original. Les commandes shell echouent avec une erreur de creation de processus, et les lectures via chemins WSL ou UNC echouent avec `EPERM`. Les demandes de permission n'ont pas debloque l'ecriture dans `/home/tankamch/projects/AEF/app`.

Pour continuer sans bloquer le projet, toutes les modifications ont ete faites dans la copie corrigee accessible sous Windows/Temp. Les fichiers sont prets a etre recopies vers le projet original lorsque l'acces WSL sera restaure. Cette contrainte est importante pour l'interpretation des tests : les tests statiques et de coherence ont ete executes sur la copie corrigee, pas sur le dossier WSL original.

<div style="page-break-after: always;"></div>

## Page 04 - Backups crees

Plusieurs backups ont ete crees avant modifications. Le backup global initial se trouve dans `backups/pre_refactor_snapshot`. Le backup de revue scientifique des CSV se trouve dans `backups/pre_csv_scientific_review_2026-06-11T00-30-17-874Z`. Le backup precedant les changements smart field et sols se trouve dans `backups/pre_smart_field_soil_2026-06-11T03-36-25-703Z`. Le backup precedant le changement de contact se trouve dans `backups/pre_contact_update_2026-06-11T04-07-46-748Z`.

Ces backups preservent les fichiers critiques avant chaque phase. L'outil `tools/rollback_selected_changes.py` permet de restaurer des fichiers depuis un backup choisi, avec `--backup` et `--files`, sans tout supprimer par defaut.

<div style="page-break-after: always;"></div>

## Page 05 - Journal des modifications

Le fichier `docs/CHANGELOG_AEF_REFACTOR.md` consigne les changements. Il inclut la refonte scientifique, la triade satellite maladie, la revue CSV, les validations, le smart field, les sols, les requirements et le contact.

Le changelog actif ne contient plus l'ancien email personnel. Le backup conserve naturellement l'etat historique, mais l'application active et les documents courants pointent vers `contact@scale-ag.tech`.

<div style="page-break-after: always;"></div>

## Page 06 - Audit initial du smart field

Avant correction, le smart field utilisait une logique simple : l'utilisateur saisissait un centre, l'application generait un carre de surface demandee, puis testait neuf positions autour du centre. La validation utilisait ESA WorldCover pour detecter grossierement l'urbain et l'eau.

Cette approche etait utile pour une premiere version, mais elle avait trois limites majeures. D'abord, elle supposait que le champ est carre. Ensuite, elle ne pouvait pas epouser une limite irreguliere ou eviter une petite route, un ruisseau ou une zone non cultivable sans deplacer tout le carre. Enfin, elle ne verifiait pas assez l'homogeneite de couverture vegetale du polygone.

<div style="page-break-after: always;"></div>

## Page 07 - Carte Step 1 preservee

L'affichage carte de l'etape `Step 1: Define Field Geography` a ete explicitement preserve. La comparaison avec le backup confirme que le coeur du bloc carte est identique : `folium.Map(... zoom_start=17, max_zoom=20)`, fond `Esri Satellite` via `World_Imagery`, `LayerControl`, dessin de polygone et edition active, puis `st_folium(... height=500, width=800, key="map_step_1")`.

Cette decision est importante parce que l'affichage existant etait deja ergonomique : satellite zoomable jusqu'aux limites de l'imagerie, puis lecture plus schematique lorsque les capacites optiques sont depassees. Les nouveaux controles ont ete ajoutes au-dessus de la carte, sans casser ce comportement.

<div style="page-break-after: always;"></div>

## Page 08 - Nouvelle entree GPS

L'entree GPS reste l'option preferee. L'utilisateur peut saisir une coordonnee sous forme decimale ou sous forme plus humaine. La coordonnee est parse avec `geopy.point.Point`, puis stockee dans `center_lat` et `center_lon`.

Apres validation de la coordonnee, l'utilisateur peut ajuster latitude et longitude manuellement avant de lancer la generation smart field. Cette etape evite de lancer un calcul de polygone sur un centre decale par une erreur de saisie ou par une geolocalisation approximative.

<div style="page-break-after: always;"></div>

## Page 09 - Nouvelle recherche par lieu

Une option additionnelle permet de chercher un lieu en langage naturel, par exemple `Yaounde Mont Mbankolo`. Cette option n'est pas censee remplacer le GPS lorsque les coordonnees existent, mais elle aide les utilisateurs non techniques qui connaissent le lieu sans connaitre latitude et longitude.

La recherche utilise `Nominatim` via `geopy`, retourne plusieurs candidats, puis laisse l'utilisateur choisir le resultat le plus proche. Une fois le resultat choisi, le centre est inscrit dans les champs latitude/longitude et reste ajustable avant la generation du champ.

<div style="page-break-after: always;"></div>

## Page 10 - Generation polygonale non carree

La nouvelle generation ne suppose plus que le champ est carre. Elle genere plusieurs familles de formes legeres : carre, rectangles allonges, rectangles tournes, losange, hexagone, octogone, trapeze et polygones avec encoche.

L'objectif n'est pas de fabriquer un cadastre exact automatiquement. L'objectif est de proposer un polygone plausible qui respecte la surface demandee, reste proche du centre, evite autant que possible les surfaces non cultivables et represente une couverture vegetale coherente. L'utilisateur peut ensuite corriger la proposition.

<div style="page-break-after: always;"></div>

## Page 11 - Respect de la superficie

Chaque candidat est scale en metres locaux pour viser la surface demandee en hectares. L'aire est recalculee avec une approximation locale latitude/longitude adaptee aux petites surfaces agricoles.

Le score penalise l'ecart relatif entre surface demandee et surface calculee. Apres chaque mouvement, rotation, redimensionnement ou edition de points, `calculate_area_ha` met a jour `area_ha`, ce qui evite que la configuration affiche une surface obsolete.

<div style="page-break-after: always;"></div>

## Page 12 - Respect du centre

Le centre saisi n'est plus traite comme une contrainte rigide impossible a ajuster. Le score accepte un petit decalage si cela permet d'eviter une route, un ruisseau, de l'eau ou de l'urbain.

La distance entre le centroide du polygone candidat et le centre demande est mesuree en metres locaux. Cette distance contribue au score, donc l'algorithme prefere rester proche du centre mais peut se decaler legerement si la couverture du sol l'exige.

<div style="page-break-after: always;"></div>

## Page 13 - Evitement des zones non cultivables

La premiere barriere utilise ESA WorldCover. Les classes `built-up`, `permanent water`, `wetland`, `mangroves`, neige/glace et autres surfaces clairement non cultivables sont penalisees.

Le score separe les surfaces cultivables ou vegetales des surfaces non cultivables. Si la proportion non cultivable devient trop elevee, le candidat est marque critique ou avertissement. Cela ne garantit pas la detection de chaque petite route, car WorldCover reste un produit raster, mais c'est une amelioration nette par rapport au carre unique.

<div style="page-break-after: always;"></div>

## Page 14 - Homogeneite de couverture vegetale

Pour eviter un polygone qui traverse plusieurs couvertures tres differentes, le score tient compte de la classe dominante WorldCover et de son pourcentage. Une classe dominante faible signale un melange : champ + route, champ + friche, champ + eau, ou plusieurs couverts.

Une seconde verification utilise Sentinel-2 NDVI : l'ecart type NDVI du polygone sert de proxy d'homogeneite vegetale. Plus la variabilite NDVI est forte, plus le score est penalise. Ce n'est pas une identification de culture parfaite, mais c'est une approximation raisonnable et legere.

<div style="page-break-after: always;"></div>

## Page 15 - Optimisation du temps de calcul

L'analyse Sentinel-2 est plus couteuse que WorldCover. Pour eviter que la generation smart field soit lente, l'application filtre d'abord tous les candidats avec WorldCover et les criteres geometriques. Ensuite, seuls les 8 meilleurs candidats sont raffines avec l'homogeneite NDVI Sentinel-2.

Cette strategie conserve l'amelioration scientifique sans surcharger le temps de chargement. Elle suit la consigne generale du projet : privilegier des algorithmes legers et utiles avant d'ajouter des modules lourds.

<div style="page-break-after: always;"></div>

## Page 16 - Edition du champ

L'edition est maintenant plus accessible. L'utilisateur peut deplacer le polygone avec un pas en metres, le tourner, le redimensionner et modifier directement les points dans un tableau.

La carte Folium garde en plus son edition native par dessin de polygone. L'utilisateur expert peut donc dessiner a la main, tandis que l'utilisateur non expert peut partir de la proposition smart field puis ajuster par boutons et table.

<div style="page-break-after: always;"></div>

## Page 17 - Metadonnees du smart field

La generation stocke maintenant `field_design_metadata`. Ces metadonnees incluent la source du champ, la forme retenue, la surface, le score, le niveau de risque, la couverture dominante, la proportion cultivable, la proportion non cultivable, la variabilite NDVI et le deplacement du centre.

Ces informations sont utiles pour l'audit et pour le dossier final. Elles rappellent que le champ automatique est une proposition calculee, pas une limite cadastrale officielle.

<div style="page-break-after: always;"></div>

## Page 18 - Audit initial des sols

Avant correction, la detection auto des sols lisait OpenLandMap avec texture `b0`, carbone organique `b0` et argile `b0`. La texture dominante determinait `field_capacity` et `wilting_point`. L'azote disponible etait derive du carbone organique avec un ratio simple.

Cette approche avait l'avantage d'etre accessible, mais elle ignorait les profondeurs du profil, ne conservait pas l'incertitude et risquait de faire croire qu'une prediction raster a 250 m est equivalente a une analyse de sol terrain.

<div style="page-break-after: always;"></div>

## Page 19 - Detection sol multi-profondeur

La correction lit les bandes de profondeur disponibles : `b0`, `b10`, `b30`, `b60` et `b100`, couvrant approximativement 0 a 1,5 m lorsque les donnees existent. Pour chaque couche, elle recupere la texture USDA, puis associe capacite au champ et point de fletrissement depuis la table pedologique interne.

Le resultat est un profil `soil_layers` multi-couches, plus coherent avec les modeles d'eau et de croissance qu'une unique couche superficielle.

<div style="page-break-after: always;"></div>

## Page 20 - Carbone, argile et nutriments

Le carbone organique et la fraction argileuse sont agreges en moyenne ponderee par epaisseur de couche. L'azote total reste une estimation derivee du carbone organique, et l'azote disponible reste un prior empirique borne.

Les valeurs P et K calculees apres detection auto restent volontairement bornees. Elles servent de point de depart pour l'utilisateur non expert, mais elles ne remplacent pas une analyse de laboratoire. Le rapport et l'interface indiquent cette limite.

<div style="page-break-after: always;"></div>

## Page 21 - Confiance de la detection sol

La detection auto ajoute `soil_data_source`, `soil_confidence` et `soil_detection_notes`. Ces champs sont stockes en session et exportes dans le JSON de configuration.

La confiance est plus faible que pour une saisie manuelle experte. Cette difference est importante parce que le selecteur de modeles de croissance doit tenir compte de la qualite des donnees sol : un sol saisi manuellement ou mesure est plus fiable qu'un raster global.

<div style="page-break-after: always;"></div>

## Page 22 - Conservation du profil sol auto

Un point corrige pendant la phase de verification : le profil auto pouvait etre ecrase par le selecteur de texture au rerun suivant. La logique preserve maintenant le profil OpenLandMap multi-couches si l'utilisateur n'a pas change manuellement la texture.

Si l'utilisateur choisit une autre texture, l'application considere qu'il s'agit d'une correction manuelle. Elle repasse `soil_data_source` a `manual`, remet la confiance a 1.0 et reconstruit une couche simple coherente avec la texture choisie.

<div style="page-break-after: always;"></div>

## Page 23 - Gestion d etat

`src/models/state_manager.py` a ete nettoye et reecrit proprement. Il initialise maintenant les nouveaux champs : `field_design_metadata`, `place_search_results`, `soil_data_source`, `soil_confidence` et `soil_detection_notes`.

La sauvegarde JSON conserve ces champs, et le chargement JSON les restaure. Cela garantit que le dossier final et les simulations utilisent la meme configuration que celle definie dans le wizard.

<div style="page-break-after: always;"></div>

## Page 24 - CSV comme source de verite

Une faiblesse heritee a ete corrigee : si les CSV etaient absents, `StateManager` recreait d'anciennes donnees codees en dur. Ces anciennes donnees contenaient des varietes et parametres que la revue scientifique avait justement remplaces.

Desormais, les CSV versionnes sont la source de verite. Si `src/data/crops_db.csv` ou `src/data/diseases_db.csv` manque, l'application signale explicitement le fichier manquant au lieu de regenerer des donnees obsoletes.

<div style="page-break-after: always;"></div>

## Page 25 - Revue scientifique des cultures

Le CSV cultures contient 13 entrees. Les varietes floues ou peu defendables ont ete remplacees par des references nommees : TME 419, TMS 30572, Obatanpa QPM, SAMMAZ 52, Coker 312, FK37, West African Amelonado, ICS 95, Norman Borlaug 100, IR64, TGx 1448-2E, Arabica Typica et Robusta Nganda.

Chaque entree possede des champs de tracabilite : nom scientifique, statut varietal, source de parametres, niveau d'evidence et notes. Les coefficients restent des priors de pilotage, pas des verites locales definitives.

<div style="page-break-after: always;"></div>

## Page 26 - Revue scientifique des maladies

Le CSV maladies contient 28 maladies. Chaque maladie inclut maintenant une famille de modele : `viral_vector`, `fungal_airborne`, `bacterial_splash` ou `soil_reservoir`. Les parametres incluent latence, persistence du reservoir, poids vectoriel, poids rain-splash, taux de saut longue distance, source et niveau d'evidence.

Ces champs repondent directement au probleme initial d'accumulation excessive : une maladie n'est plus seulement une incidence qui monte mecaniquement vers 100 %. La dynamique depend du type de pathogene, de la latence, du reservoir, du climat, du vecteur et de la possibilite de resolution partielle.

<div style="page-break-after: always;"></div>

## Page 27 - Modele maladie tau-leaping

Le moteur maladie introduit une logique stochastique tau-leaping. L'objectif est de sortir d'une reaction-diffusion circulaire et deterministe. Les maladies peuvent produire des foyers, des sauts et des incertitudes.

Le modele conserve des etats latents, infectieux, resolus et reservoir. Il gere differemment les maladies virales vectorielles, fongiques aeriennes, bacteriennes par splash et maladies a reservoir sol/residu. Pour les vivaces, la persistence est longue mais finie, ce qui evite une saturation permanente irrealiste.

<div style="page-break-after: always;"></div>

## Page 28 - Roguing et balance rendement

La logique de roguing doit toujours comparer deux effets : le gain par reduction d'inoculum et la perte de rendement due a la destruction de plantes productives. Le moteur integre cette idee dans les scenarios d'intervention.

Le dossier doit donc eviter les recommandations simplistes du type supprimer automatiquement tout foyer. Pour les vivaces, l'abattage ou la taille severe a un cout de rendement durable. Pour les annuelles, la suppression peut etre pertinente si le foyer est localise et le gain epidemiologique attendu depasse la perte de peuplement.

<div style="page-break-after: always;"></div>

## Page 29 - Detection satellite maladie

La detection satellite automatique est conservee. Elle ne pretend pas identifier directement un pathogene depuis la canopee. Elle detecte une anomalie et propose une liste de maladies plausibles compatibles avec la culture, le contexte et les signatures disponibles.

Le systeme selectionne la maladie la plus probable, mais garde les alternatives pour validation en un clic. Cette prudence est indispensable : une baisse NDVI ou NDMI peut venir d'une maladie, d'un stress hydrique, d'un sol, d'un ombrage, d'une carence ou d'une erreur d'image.

<div style="page-break-after: always;"></div>

## Page 30 - Calibration adaptative

Le module de calibration adaptative reste central. Il doit absorber les erreurs entre simulation et terrain a mesure que l'utilisateur ajoute rendement, nutriments ou incidence maladie.

La version legere actuelle conseille la prochaine mesure utile lorsque la maladie accelere ou lorsque le stress nutritif est fort. La cible de recherche reste un modele bayesien etat-espace avec filtres particulaires et design experimental actif. Cette trajectoire est documentee dans les fichiers scientifiques.

<div style="page-break-after: always;"></div>

## Page 31 - Selecteur de modele de croissance

Le selecteur de croissance choisit la famille cible selon le contexte : AquaCrop/CROPWAT pour l'eau et les cultures herbacees quand les donnees sont simples, DSSAT/APSIM pour les cultures annuelles avec donnees suffisantes, STICS/APSIM pour les vivaces et cycles longs, et AEF-lite comme fallback.

Cette architecture evite de presenter STICS-lite comme modele principal universel. Elle reconnait que le meilleur modele depend des donnees disponibles, de la culture, du stress dominant et du niveau de precision attendu.

<div style="page-break-after: always;"></div>

## Page 32 - Optimisation irrigation

L'optimisation irrigation doit cibler les periodes de stress hydrique qui menacent le rendement, pas seulement remplir le sol de maniere uniforme. Le moteur simule la reserve utile, l'ET0, la demande culturale et les pertes de rendement associees.

Le dossier compare les recommandations a un scenario sans action. Il peut aussi distinguer une strategie optimale d'une strategie minimale utile, afin d'aider les producteurs sous contrainte de ressources.

<div style="page-break-after: always;"></div>

## Page 33 - Optimisation fertilisation

La fertilisation part des stocks initiaux N/P/K, de la culture, de la phase de croissance et du stress nutritif. Les valeurs issues d'OpenLandMap servent de prior pour non expert, mais doivent etre corrigees par mesures terrain.

La recommandation doit rester prudente : les doses ne sont pas seulement une maximisation du rendement, mais aussi un compromis entre cout, risque de lessivage, disponibilite produit, calendrier et impact agronomique.

<div style="page-break-after: always;"></div>

## Page 34 - Optimisation date de semis

La date de semis doit exploiter meteo, climat, modele de croissance et risques de maladie. L'objectif est de choisir une fenetre qui reduit les periodes critiques de stress hydrique, thermique, nutritif ou biotique.

Pour certaines maladies comme Fusarium head blight sur ble, la phenologie est centrale : eviter une floraison en fenetre chaude et humide peut etre plus efficace qu'une correction tardive.

<div style="page-break-after: always;"></div>

## Page 35 - Internationalisation

Une base d'internationalisation legere existe avec `src/utils/i18n.py`. Elle introduit une selection de langue et des traductions pour les zones deja touchees, notamment l'authentification et une partie du rapport.

Limite restante : l'application n'est pas encore internationalisee a 100 %. Beaucoup de libelles Step 1 a Step 5 restent en anglais. Il faudra poursuivre l'extraction de tous les textes visibles vers le registre FR/EN.

<div style="page-break-after: always;"></div>

## Page 36 - Spinners et messages utilisateur

Les operations longues ont des spinners : detection satellite maladie, generation du champ, lecture sol, simulation, ensemble maladie, optimisations et potentiel de rendement. Les nouveaux messages sont volontairement compréhensibles pour un utilisateur non technique : recherche du lieu, scan vegetation/routes/eau, lecture des couches sol, comparaison de scenarios.

Limite restante : certaines zones anciennes utilisent encore des messages techniques ou anglais. Elles doivent etre harmonisees dans la prochaine passe i18n.

<div style="page-break-after: always;"></div>

## Page 37 - Requirements

Le fichier `requirements.txt` a ete complete. Les dependances geospatiales etaient deja presentes : Earth Engine, Folium, streamlit-folium, geopy et geocoder. `branca` a ete ajoute car Folium l'utilise directement.

Des extensions Flask importees dans le projet mais absentes du fichier ont ete ajoutees : `Flask-Login`, `Flask-Bcrypt`, `Flask-DebugToolbar` et `Flask-SQLAlchemy`. La liste actuelle contient 24 entrees.

<div style="page-break-after: always;"></div>

## Page 38 - Contact acces

Le contact pour obtenir un code d'acces a ete remplace dans `app.py`. Le lien affiche maintenant `contact@scale-ag.tech` avec `mailto:contact@scale-ag.tech`.

La passe de test confirme que l'ancien contact personnel n'apparait plus dans les fichiers actifs audites. Les backups historiques peuvent encore contenir l'ancien etat, ce qui est normal pour un backup.

<div style="page-break-after: always;"></div>

## Page 39 - Rollback

Le fichier `tools/rollback_selected_changes.py` permet une restauration selective. Il peut lister les fichiers disponibles dans un backup, restaurer quelques fichiers ou restaurer tout un backup. Il ne supprime pas les nouveaux fichiers sauf si l'option explicite `--delete-new-files` est utilisee.

Exemple pour restaurer seulement les CSV depuis leur backup : `python tools/rollback_selected_changes.py --backup backups/pre_csv_scientific_review_2026-06-11T00-30-17-874Z --files src/data/crops_db.csv src/data/diseases_db.csv`.

<div style="page-break-after: always;"></div>

## Page 40 - Fichiers principaux modifies

Fichiers fonctionnels principaux : `pages/main/setup_page.py`, `src/models/state_manager.py`, `app.py`, `requirements.txt`, `src/models/simulation_engine.py`, `src/models/disease_service.py`, `pages/main/report.py`, `pages/main/surveillance.py`.

Fichiers de modeles ajoutes : `src/models/disease_models.py`, `src/models/growth_model_selector.py`, `src/models/adaptive_calibration.py`, `src/models/satellite_disease_triage.py`.

Fichiers docs et support : `docs/SCIENTIFIC_MODELS.md`, `docs/CSV_SCIENTIFIC_REVIEW.md`, `docs/GEOSPATIAL_SOIL_AUDIT.md`, `docs/CHANGELOG_AEF_REFACTOR.md`, `support/test_results/aef_50_targeted_tests.json`, `support/test_results/aef_1000_checks.json`.

<div style="page-break-after: always;"></div>

## Page 41 - Phase 50 tests - methode

La phase de 50 tests demandee a ete executee avec un validateur statique JS, car l'environnement actuel ne permet pas de lancer Python, Streamlit ou un shell WSL. Les tests ciblent les garanties essentielles : carte preservee, smart field, sols, etat, contact, requirements, CSV, backups et documentation.

Chaque test retourne un nom, un statut et un detail. Le resultat complet est stocke dans `support/test_results/aef_50_targeted_tests.json`.

<div style="page-break-after: always;"></div>

## Page 42 - Phase 50 tests - resultats globaux

Resultat : 50/50 tests reussis, 0 echecs.

Aucun echec n'a ete detecte dans cette passe. Aucune correction supplementaire n'a donc ete necessaire apres la relance des 50 tests. Les tests confirment notamment que le coeur de la carte Step 1 est intact, que l'email de contact est correct, que les requirements critiques sont presents, que les backups existent et que les CSV gardent leurs champs scientifiques.

<div style="page-break-after: always;"></div>

## Page 43 - Tests 1 a 10

- 01 Step 1 map core unchanged: OK
- 02 Satellite basemap retained: OK
- 03 Map zoom max 20 retained: OK
- 04 Map drawing polygon enabled: OK
- 05 Place search UI present: OK
- 06 GPS preferred UI present: OK
- 07 Center adjustment fields present: OK
- 08 Smart field button present: OK
- 09 Non-square candidate generator present: OK
- 10 Candidate area scoring present: OK

<div style="page-break-after: always;"></div>

## Page 44 - Tests 11 a 20

- 11 Non-cultivable scoring present: OK
- 12 Cultivable scoring present: OK
- 13 Dominant cover scoring present: OK
- 14 NDVI homogeneity function present: OK
- 15 NDVI limited to shortlist: OK
- 16 WorldCover dataset present: OK
- 17 Manual polygon validation retained: OK
- 18 Move polygon controls present: OK
- 19 Rotate polygon controls present: OK
- 20 Resize polygon controls present: OK

<div style="page-break-after: always;"></div>

## Page 45 - Tests 21 a 30

- 21 Vertex editor present: OK
- 22 Area recalculation after edits: OK
- 23 Field metadata saved by setup: OK
- 24 Soil auto button present: OK
- 25 Soil depth bands present: OK
- 26 Soil texture dataset present: OK
- 27 Soil carbon dataset present: OK
- 28 Soil clay dataset present: OK
- 29 Soil confidence metadata present: OK
- 30 Soil source metadata present: OK

<div style="page-break-after: always;"></div>

## Page 46 - Tests 31 a 40

- 31 Auto soil profile preserved on rerun: OK
- 32 Manual soil override resets source: OK
- 33 State defaults include field metadata: OK
- 34 State defaults include soil metadata: OK
- 35 State saves field metadata: OK
- 36 State loads field metadata: OK
- 37 State saves soil metadata: OK
- 38 State loads soil metadata: OK
- 39 State no hard-coded old CSV fallback: OK
- 40 State CSV truth guard present: OK

<div style="page-break-after: always;"></div>

## Page 47 - Tests 41 a 50

- 41 Contact email changed in app: OK
- 42 Old contact absent active files: OK
- 43 Flask extension requirements present: OK
- 44 Geospatial requirements present: OK
- 45 Crop CSV count 13: OK - 13
- 46 Disease CSV count 28: OK - 28
- 47 Crop CSV has scientific traceability: OK
- 48 Disease CSV has model fields: OK
- 49 Backups present: OK
- 50 Audit and manifest updated: OK

<div style="page-break-after: always;"></div>

## Page 48 - Limites restantes

Les principales limites restantes sont liees a l'environnement, aux donnees et a l'integration de backends scientifiques externes. L'environnement Codex de cette session n'a pas permis de lancer Streamlit ni Python ; il faudra donc refaire une validation runtime dans un environnement normal.

WorldCover et OpenLandMap restent des produits globaux a resolution limitee. Ils peuvent manquer des petits chemins, canaux, limites cadastrales ou variations intra-parcellaires. Les recommandations doivent donc rester editables et prudentes.

Les backends APSIM, DSSAT, AquaCrop, CROPWAT et STICS ne sont pas encore integres comme moteurs executables complets. Le selecteur de modele documente la famille cible et garde AEF-lite en fallback.

<div style="page-break-after: always;"></div>

## Page 49 - Prochaines priorites

Priorite 1 : recopier la copie corrigee dans le workspace WSL original lorsque l'acces est restaure, puis lancer `streamlit run app.py`.

Priorite 2 : faire une validation runtime utilisateur : login, Step 1 GPS, Step 1 recherche lieu, generation smart field, edition polygonale, Step 2 culture, Step 3 satellite ou manuel, Step 4 sol auto, Step 5 simulation, dashboard et PDF.

Priorite 3 : poursuivre l'internationalisation complete FR/EN.

Priorite 4 : remplacer progressivement les priors moyens par donnees de terrain pilotes et publications regionales.

<div style="page-break-after: always;"></div>

## Page 50 - Conclusion

La copie corrigee d'AEF Crop Intelligence est plus robuste scientifiquement et plus accessible a l'utilisateur non expert. Le smart field n'est plus limite au carre, la recherche par lieu complete le GPS, la carte parfaite de Step 1 est preservee, les sols automatiques sont mieux documentes et moins trompeurs, les CSV sont plus defendables, la maladie est modelisee de facon plus realiste, et la validation statique ciblee passe sans echec.

Le point bloquant restant n'est pas fonctionnel dans la copie corrigee, mais operationnel : il faut pouvoir ecrire dans le workspace WSL original et lancer l'application dans un environnement Python normal pour confirmer le comportement en interface.

<div style="page-break-after: always;"></div>


## Addendum 2026-06-11 - Dossier scenarios and roguing safeguards

The generated decision dossier now has to compare four intervention levels: no action, minimum useful action, intermediate balanced action, and optimized recommendation. The intermediate level is designed as a realistic adoption path: it uses a practical share of the optimized irrigation and fertilization calendar and applies disease control with a less aggressive intensity than the optimized plan.

Roguing, severe pruning, and plant or tree removal must not be presented as automatic disease responses. The disease scenario engine evaluates two opposing effects before applying removal: the expected epidemiological gain from lowering inoculum pressure and the yield cost caused by removing productive plants or canopy. Annual crops can justify removal when the focus is localized and the expected epidemiological gain exceeds stand loss. Perennial crops carry a stricter margin because tree removal or severe pruning can reduce yield over several seasons.

The dossier now exposes this balance in the scenario chapter by reporting, for minimum, intermediate, and optimized scenarios, the probability of roguing/pruning application across ensemble runs, the yield penalty, the inoculum benefit score, and the yield cost score. This prevents simplistic recommendations such as removing every detected focus and keeps the final advice aligned with the modeled yield trade-off.
