# AEF Crop Intelligence - Guide pas a pas

Bienvenue dans AEF Crop Intelligence. Ce guide explique comment utiliser l'application depuis l'accueil jusqu'au rapport final, meme si vous decouvrez l'outil pour la premiere fois.

L'objectif est simple : vous aider a decrire votre champ, lancer une simulation agronomique, comprendre les stress futurs, comparer plusieurs strategies de gestion, puis exporter un dossier clair pour prendre une decision.

---

## 🗺️ Carte rapide des modules

| Symbole | Module | A quoi cela sert |
|---|---|---|
| 🔐 | Acces | Choisir la langue, entrer le code d'acces et ouvrir l'application. |
| 🌍 | Configuration | Decrire la parcelle, la culture, le sol, la maladie et l'economie. |
| 🤝 | Cooperative | Gerer plusieurs petites parcelles dans un meme perimetre agricole. |
| 🛰️ | Dashboard | Lire l'etat simule du champ et les stress agronomiques. |
| 🧭 | Recommandations | Comparer ce qui se passe sans action, avec optimum agronomique et avec optimum economique. |
| 🔎 | Pré-évaluation | Tester avant plantation si une variété est adaptée à une parcelle encore non cultivée. |
| 🧪 | What-if | Modifier un calendrier conseille et voir l'effet sur rendement et retour economique. |
| 🗃️ | Rapport | Telecharger le dossier complet pour garder une trace ou le partager. |
| 📄 | PDF | Export lisible pour l'utilisateur, le technicien ou le responsable agricole. |
| 💾 | JSON | Export technique pour recharger une configuration ou archiver les donnees. |

---

# Partie 1 - Utilisation en francais

## 1. Avant de commencer

AEF Crop Intelligence fonctionne mieux si vous avez quelques informations de base sur votre champ. Vous pouvez tout de meme utiliser l'application avec des detections automatiques lorsque vous n'avez pas toutes les donnees.

Preparez si possible :

1. La position du champ : coordonnees GPS du centre, nom du lieu, ou possibilite de dessiner le champ sur la carte.
2. La superficie approximative.
3. La culture et, si possible, la variete.
4. La date de plantation ou de mise en place.
5. Les observations visibles : jaunissement, taches, foyers de maladie, manque d'eau, croissance faible.
6. Les informations de sol si vous les connaissez : texture, pH, matiere organique, azote, phosphore, potassium, capacite de retention en eau.
7. Les couts locaux : prix de vente de la production, couts d'engrais, eau, main-d'oeuvre, traitements, services.

Vous n'etes pas oblige d'avoir toutes ces informations. L'application propose des valeurs par defaut et des detections automatiques, mais les resultats seront plus prudents lorsque les donnees sont incertaines.

## 2. Ouvrir l'application et choisir la langue 🔐

1. Ouvrez AEF Crop Intelligence.
2. Sur la page d'accueil, choisissez la langue dans le selecteur de langue.
3. Entrez votre code d'acces.
4. Cliquez sur le bouton de connexion.
5. Attendez que l'espace de travail se charge.

Si l'application affiche un message d'erreur de code, verifiez le code fourni. Si vous n'en avez pas, contactez l'adresse indiquee dans l'application.

Important : choisissez la langue des le debut. Le choix doit s'appliquer aux pages, aux alertes et aux rapports exportes.

## 3. Choisir le mode de travail

Au debut, vous devez choisir le type d'analyse.

### Mode Parcelle unique

Choisissez ce mode si vous analysez un seul champ ou un grand bloc agricole continu.

Ce mode est adapte lorsque :

1. La parcelle est d'un seul tenant.
2. La culture et la variete sont les memes sur l'ensemble du champ.
3. Vous voulez un diagnostic et des recommandations pour une exploitation individuelle.
4. Vous voulez un calendrier d'irrigation, de fertilisation et de controle maladie pour ce champ.

### Mode Cooperative 🤝

Choisissez ce mode si vous gerez plusieurs petites parcelles dans un meme perimetre.

Ce mode est adapte lorsque :

1. Plusieurs producteurs sont regroupes dans une zone commune.
2. Les parcelles sont petites, dispersees ou irregulieres.
3. Une cooperative, une societe agricole ou un responsable terrain veut une vue globale.
4. Vous voulez identifier, nommer et corriger plusieurs parcelles.
5. Vous souhaitez un dashboard et un rapport adaptes a plusieurs parcelles.

Dans ce mode, l'application considere pour l'instant que toutes les parcelles ont la meme culture et la meme variete, sauf pour certains parametres que vous pouvez adapter parcelle par parcelle.


### Mode Pré-évaluation 🔎

Choisissez ce mode si rien n'est encore planté et que vous voulez savoir si une variété donnée mérite d'être installée sur une parcelle candidate.

Ce mode est adapté lorsque :

1. Vous avez identifié une parcelle possible, mais la culture n'est pas encore en place.
2. Vous voulez comparer le climat, le sol, les besoins en eau, les besoins en fertilisation et les risques de maladie avant d'investir.
3. Vous voulez connaître la meilleure fenêtre de plantation parmi les prochains mois.
4. Vous voulez obtenir un score de suitabilité clair sur 100.
5. Vous voulez un PDF expliquant pourquoi il est recommandé de planter, de planter avec prudence ou de ne pas prioriser cette variété.

Le mode Pré-évaluation ressemble au mode Parcelle unique, mais il travaille avant plantation. Pour les cultures vivaces, il n'évalue qu'un seul cycle de production, pas un horizon de plusieurs années.

## 4. Definir la geographie en mode Parcelle unique 🌍

La geographie est la premiere etape importante. Elle dit a l'application ou se trouve le champ et quelle surface analyser.

### Methode A - Utiliser les coordonnees GPS

1. Choisissez l'option de definition par coordonnees.
2. Entrez la latitude et la longitude du centre du champ.
3. Vous pouvez utiliser le format decimal, par exemple 9.4628, 14.1458.
4. Vous pouvez aussi utiliser le format degre-minute-seconde-cardinalite, par exemple 9 deg 27 min 46 sec N et 14 deg 8 min 45 sec E.
5. Entrez la superficie approximative du champ.
6. Cliquez sur le bouton qui genere le champ ou le smart field.
7. Regardez la carte : l'application propose un contour de champ.
8. Corrigez le contour si la proposition ne suit pas bien les limites reelles.

### Methode B - Rechercher un lieu

Utilisez cette option si vous n'avez pas les coordonnees GPS.

1. Entrez un lieu connu, par exemple le village, le quartier, le terroir ou un point proche.
2. Lancez la recherche.
3. Verifiez la position proposee sur la carte.
4. Deplacez ou ajustez le point si necessaire.
5. Lancez ensuite la generation du champ autour de ce point.
6. Corrigez le polygone si le contour traverse une route, un ruisseau, un batiment ou une zone non cultivee.

### Methode C - Dessiner le champ a la main

1. Ouvrez l'outil de dessin sur la carte.
2. Cliquez autour du champ pour former le polygone.
3. Fermez le polygone.
4. Verifiez la superficie calculee.
5. Corrigez les sommets si les limites ne sont pas exactes.

Cette methode est souvent la meilleure si vous connaissez bien les limites du terrain.

## 5. Comprendre la carte

La carte sert a verifier que l'application travaille sur la bonne zone.

1. Zoomez pour voir le champ.
2. Dezoomez pour verifier le contexte : routes, cours d'eau, villages, autres cultures.
3. Comparez le contour propose avec votre connaissance du terrain.
4. Evitez d'inclure les zones non cultivees.
5. Evitez d'inclure une autre culture si le champ voisin est different.
6. Pour une culture perenne, verifiez que le contour suit bien la plantation reelle.

Si vous voyez une image satellite claire, utilisez-la. Si le zoom depasse la resolution optique disponible, la carte peut passer a une vue plus schematique. C'est normal.

## 6. Definir le perimetre en mode Cooperative 🤝

Le mode Cooperative commence par le perimetre general, puis l'application detecte les parcelles a l'interieur.

1. Choisissez le mode Cooperative sur l'accueil ou la configuration.
2. Definissez le perimetre de la cooperative avec des coordonnees, une recherche de lieu ou un dessin manuel.
3. Verifiez que le perimetre contient les parcelles a analyser.
4. Lancez la detection automatique des parcelles.
5. Attendez la fin du traitement. L'application tente d'abord une detection interne guidee par Sentinel-2 et WorldCover : elle analyse les pixels vegetes/cultivables dans le perimetre, segmente l'image et convertit les segments en polygones editables.
6. Si Sentinel-2 est indisponible, trop nuageux, trop peu informatif ou si le perimetre est trop grand, l'application utilise un fallback geometrique. Ce fallback cree des parcelles candidates plausibles, irregulieres et non chevauchantes, avec une fine separation visible entre parcelles voisines au lieu de les coller dans un seul bloc artificiel.
7. Sur la carte, les parcelles utilisent des couleurs contrastees inspirees de la lecture en quatre couleurs, plus un contour blanc. Cela aide a voir les frontieres fines meme quand la couverture vegetale semble continue.
8. L'application affiche aussi la surface cultivee detectee, la surface non assignee/non cultivee et la fraction cultivee. Une grande surface non assignee n'est pas automatiquement une erreur : elle peut correspondre a des routes, drains, batiments, eau, jacheres ou espaces sans culture.
9. Lisez la methode utilisee, la confiance moyenne et la precision estimee des limites. Une precision faible signifie que vous devez corriger les polygones avec attention et, lorsque l'integration sera activee, utiliser les limites FTW pre-calculees comme secours gratuit.
10. Lisez la carte avec toutes les parcelles detectees.
11. Supprimez une parcelle detectee par erreur.
12. Redessinez une parcelle si son contour est mauvais.
13. Ajoutez une parcelle manquante avec l'outil polygone.
14. Donnez un nom simple a chaque parcelle, par exemple Producteur A - champ 1, Bloc Nord, Parcelle Moussa, Cacao 03.
15. Verifiez que les noms sont comprehensibles pour l'equipe terrain.
16. Enregistrez la configuration.

Les parcelles detectees ne doivent pas se chevaucher. Elles ne sont pas obligees d'etre collees : une limite mince et lisible entre deux parcelles est normale et doit etre preservee. L'application ne cherche plus a remplir tout le perimetre ; les grands creux sont acceptes, mais vous devez verifier qu'ils ne correspondent pas a des parcelles oubliees. Si vous voyez un chevauchement, corrigez-le avant de continuer.

## 7. Nommer les parcelles en mode Cooperative

Le nom de parcelle est tres important. Il evite de confondre les producteurs et les recommandations.

Conseils :

1. Utilisez un nom court.
2. Evitez les noms identiques.
3. Ajoutez un repere utile : producteur, village, bloc, numero, position.
4. Verifiez que le nom apparait correctement dans les tableaux et les cartes.
5. Gardez les memes noms dans vos fiches terrain.

Ces noms doivent etre sauvegardes dans le fichier JSON de configuration.

## 8. Definir la culture et la variete

Apres la geographie, choisissez la culture.

1. Ouvrez la section culture ou systeme de culture.
2. Selectionnez la culture : cacao, mais, manioc, coton, ble, riz, etc.
3. Selectionnez la variete lorsque l'application le propose.
4. Entrez la date de plantation, semis ou mise en place.
5. Pour une culture annuelle, l'application utilise automatiquement la duree du cycle pour determiner l'horizon jusqu'a la recolte.
6. Pour une culture perenne, l'application peut utiliser un horizon de plusieurs annees, car il y a plusieurs periodes de recolte.
7. Verifiez les informations de cycle, de sensibilite, de rendement potentiel et de specificites agronomiques.

Si vous ne connaissez pas la variete exacte, choisissez la plus proche et restez prudent dans l'interpretation.

## 9. Comprendre les cultures annuelles et perennes

### Cultures annuelles

Une culture annuelle a un cycle limite. Exemple : mais, coton, riz, ble, soja, arachide.

Dans ce cas :

1. L'horizon d'analyse va de la date de plantation a la date de recolte prevue.
2. Vous n'avez pas besoin de choisir un nombre d'annees.
3. Les recommandations visent le cycle en cours.
4. Le rendement attendu correspond a la recolte de ce cycle.

### Cultures perennes

Une culture perenne reste en place plusieurs annees. Exemple : cacao, cafe, palmier, bananier selon le systeme, certains vergers.

Dans ce cas :

1. L'horizon economique peut etre configure.
2. L'application doit tenir compte de plusieurs recoltes.
3. Les couts lourds, comme taille severe ou abattage, peuvent avoir des effets durables.
4. Les maladies peuvent persister, baisser en pression, revenir avec la saison ou rester dans des reservoirs.
5. Les recommandations doivent etre interpretees sur la duree.

## 10. Configurer la maladie ou le stress biotique

L'application peut travailler avec une maladie selectionnee manuellement ou avec une detection automatique qui signale un probleme probable de canopee.

### Detection automatique

1. Choisissez la detection automatique si vous ne savez pas quelle maladie est presente.
2. L'application analyse les signaux disponibles, notamment la canopee observee par satellite.
3. Elle peut proposer une maladie probable ou plusieurs possibilites.
4. Validez la possibilite la plus plausible si vous avez des observations terrain.
5. Si vous n'etes pas certain, gardez une interpretation prudente.
6. La date de detection doit correspondre a la date du jour lorsque la detection automatique est lancee.

La detection automatique ne remplace pas un diagnostic de terrain. Elle sert a orienter la surveillance.

### Selection manuelle d'une maladie

1. Choisissez la maladie dans la liste.
2. Indiquez la date d'observation.
3. Placez les foyers de maladie sur la carte si l'interface le permet.
4. Indiquez le nombre approximatif de plantes touchees ou la severite.
5. Ajoutez plusieurs foyers si la maladie apparait en plusieurs points.
6. Verifiez que les foyers sont bien situes dans le champ.

### Cas du mode Cooperative

En mode Cooperative, les foyers peuvent concerner une ou plusieurs parcelles.

1. Affichez la carte des parcelles.
2. Selectionnez la parcelle concernee.
3. Ajoutez ou corrigez les foyers.
4. Repetez pour les autres parcelles si necessaire.
5. Gardez une coherence entre le terrain et la carte.

## 11. Comprendre le roguing, la taille et les interventions maladie

Le roguing consiste a supprimer une plante malade ou un foyer. Ce n'est pas automatiquement une bonne decision.

L'application doit comparer deux effets :

1. Le gain attendu : moins d'inoculum, donc moins de propagation future.
2. Le cout agronomique : perte d'une plante productive, perte de peuplement ou perte durable de canopee.

Pour une culture annuelle :

1. Supprimer quelques plantes peut etre utile si le foyer est petit et tres dangereux.
2. Supprimer trop de plantes peut reduire le rendement plus que la maladie elle-meme.
3. L'intervention doit etre proportionnee.

Pour une culture perenne :

1. Abattre ou tailler severement peut couter plusieurs recoltes.
2. Il faut confirmer la maladie avant de detruire une plante productive.
3. La saison, la dormance, le pruning normal, la pression de maladie et les reservoirs doivent etre consideres.

## 12. Configurer le sol

La configuration du sol aide l'application a estimer l'eau disponible, la fertilite et les stress abiotiques.

### Detection automatique du sol

1. Lancez la detection automatique si vous n'avez pas d'analyse de sol.
2. L'application estime les proprietes a partir de bases geographiques disponibles.
3. Verifiez si les valeurs semblent plausibles pour la zone.
4. Utilisez cette option comme point de depart.

Les donnees automatiques sont utiles, mais moins precises qu'une analyse locale.

### Configuration manuelle

Utilisez cette option si vous avez des observations ou une analyse de sol.

1. Entrez la texture si vous la connaissez : sableux, limoneux, argileux, etc.
2. Entrez le pH.
3. Entrez la matiere organique.
4. Entrez les nutriments initiaux si disponibles.
5. Entrez l'eau initiale ou l'humidite si disponible.
6. Verifiez les unites.

### Configuration expert

Cette option est destinee aux utilisateurs plus avances.

1. Modifiez les parametres plus techniques seulement si vous les comprenez.
2. Gardez les valeurs par defaut si vous n'avez pas de mesure fiable.
3. Notez les modifications importantes pour pouvoir expliquer les resultats.

### Sol en mode Cooperative

En mode Cooperative, le sol peut etre globalement configure pour le perimetre, mais certains elements peuvent varier par parcelle.

1. Affichez la carte des parcelles pendant la configuration du sol.
2. Verifiez quelle parcelle vous modifiez.
3. Entrez les nutriments initiaux par parcelle si l'information existe.
4. Entrez l'historique d'utilisation par parcelle, par exemple nombre d'annees cultivees sans fertilisation.
5. Utilisez les noms de parcelles pour eviter les erreurs.

## 13. Configurer l'economie

L'economie permet de comparer une strategie tres bonne agronomiquement avec une strategie reellement rentable.

Ouvrez la configuration economique et renseignez :

1. La devise.
2. Le prix de vente de la production.
3. La source du prix : manuel, marche local, estimation, reference regionale.
4. Les prix des engrais.
5. Le cout de l'eau ou de l'irrigation.
6. Le cout de main-d'oeuvre par jour et par hectare lorsque c'est demande.
7. Les couts de traitement : fongicide, biocontrole, service de pulverisation.
8. Les couts de remplacement de plantes.
9. Les couts de scouting ou prospection.
10. Les couts de taille, pruning ou roguing si applicable.

Si le prix source change, verifiez que les valeurs affichees changent ou que l'application explique pourquoi elles restent manuelles.

## 14. Sauvegarder et recharger une configuration 💾

L'application peut sauvegarder une configuration en JSON.

### Sauvegarder

1. Terminez la configuration du champ.
2. Cliquez sur l'option de telechargement JSON si disponible.
3. Conservez le fichier avec un nom clair.
4. Exemple de nom : cacao_mbankolo_2026_config.json.

### Recharger

1. Ouvrez l'application.
2. Chargez le fichier JSON de configuration.
3. Verifiez la carte, la culture, le sol, l'economie et les maladies.
4. Corrigez ce qui a change depuis la derniere utilisation.

Le JSON est utile pour l'archivage et la reprise du travail. Pour un agriculteur ou un responsable terrain, le PDF reste plus lisible.

## 15. Lancer le dashboard 🛰️

Le dashboard resume l'etat du champ et les predictions.

1. Assurez-vous que la configuration est complete.
2. Ouvrez la page Dashboard.
3. Attendez la fin des calculs si un spinner s'affiche.
4. Choisissez la date a laquelle vous voulez voir l'etat du champ.
5. Pour le futur, utilisez le calendrier de date de prevision.
6. Lisez les indicateurs principaux : rendement prevu, stress hydrique, stress nutritif, stress maladie, incertitude.
7. Consultez les cartes si elles sont disponibles.
8. Comparez les resultats avec votre connaissance terrain.

Le dashboard ne donne pas une certitude absolue. Il donne une estimation prudente a partir des donnees disponibles.

## 16. Comprendre le reality check

Le reality check compare des observations reelles passees avec la simulation.

Il est pertinent uniquement entre :

1. La date de plantation.
2. La date actuelle ou la date d'observation disponible.

Il ne faut pas comparer une simulation future avec une observation satellite future qui n'existe pas encore.

Quand le reality check est disponible :

1. Regardez si la tendance simulee semble proche des observations.
2. Verifiez si l'ecart est petit ou grand.
3. Si l'ecart est grand, les parametres de sol, culture, date, maladie ou meteo doivent peut-etre etre corriges.
4. Utilisez la surveillance adaptative pour ameliorer progressivement le modele.

## 17. Lire les marges d'erreur

Les marges d'erreur rappellent que l'application est un outil prudent.

Une marge large signifie :

1. Donnees incompletes.
2. Incertitude sur le sol.
3. Incertitude sur la maladie.
4. Incertitude sur les couts economiques.
5. Peu de mesures terrain recentes.

Une marge plus faible signifie que l'application a plus d'information fiable, surtout si la surveillance adaptative a recu des mesures terrain.

N'interpretez pas un chiffre unique comme une certitude. Regardez toujours l'intervalle et la logique agronomique.


## 17A. Utiliser le mode Pré-évaluation 🔎

Le mode Pré-évaluation sert à décider avant plantation. Il ne part pas d'un champ déjà cultivé, mais d'une parcelle candidate et d'une variété que vous envisagez de planter.

Suivez les étapes :

1. Choisissez le mode Pré-évaluation sur l'accueil.
2. Donnez un nom à la parcelle candidate.
3. Entrez le centre GPS ou positionnez la parcelle sur la carte.
4. Entrez la superficie approximative.
5. Cliquez sur Générer la parcelle candidate si vous voulez un contour simple.
6. Cliquez sur Optimiser la parcelle candidate avec la couverture satellite si vous voulez que l'application cherche une zone plus plausible autour du centre, en évitant autant que possible les surfaces non cultivables visibles.
7. Dessinez ou corrigez manuellement le polygone sur la carte si nécessaire.
8. Sélectionnez la culture et la variété.
9. Vérifiez si la culture est annuelle ou vivace. Pour une vivace, l'analyse reste limitée à un cycle.
10. Entrez la date la plus proche à partir de laquelle vous accepteriez de planter.
11. Configurez le sol manuellement ou utilisez la détection automatique du sol.
12. Lancez la pré-évaluation.
13. Lisez le score de suitabilité sur 100.
14. Lisez la meilleure date de plantation proposée.
15. Consultez les calendriers d'irrigation et de fertilisation proposés pour le cycle.
16. Consultez les risques de maladie issus de la base de pression maladie documentée par la littérature.
17. Téléchargez le PDF de pré-évaluation.

Le score combine plusieurs composantes : climat, faisabilité hydrique, sol et nutriments, pression maladie, fenêtre de plantation et confiance des données. Une note élevée ne remplace pas une visite de terrain, une analyse de sol ou la surveillance locale des maladies. Elle indique seulement que la parcelle semble favorable selon les données disponibles.

## 18. Ouvrir la page Recommandations 🧭

La page Recommandations sert a transformer le diagnostic en plan d'action.

1. Ouvrez la page Recommandations.
2. Verifiez le resume de configuration.
3. Pour une culture annuelle, ne cherchez pas d'horizon en annees : le cycle va automatiquement jusqu'a la recolte prevue.
4. Pour une culture perenne, choisissez l'horizon economique si l'interface le demande.
5. Cliquez sur Run recommendation optimization ou son equivalent en francais.
6. Attendez la fin du calcul.
7. Lisez les onglets de resultats.

L'optimisation ne doit pas se lancer automatiquement a l'ouverture. Vous gardez le controle du moment ou elle demarre.

## 19. Comprendre les trois strategies

La page Recommandations compare au moins trois situations.

### Baseline ou no action

C'est ce qui se passe si vous ne faites rien de plus que la situation actuelle.

A regarder :

1. Production attendue.
2. Revenu net attendu.
3. Stress restant.
4. Risque maladie.
5. Niveau d'incertitude.

Le gain net de la baseline ne doit pas etre confondu avec zero. La baseline a un revenu, des couts et un resultat net. Ce qui vaut zero, c'est seulement le gain supplementaire par rapport a elle-meme.

### Optimum agronomique

C'est la strategie qui cherche a reduire au maximum les stress et a proteger la production.

Elle peut recommander :

1. Plus d'irrigation.
2. Plus de fertilisation.
3. Plus de surveillance.
4. Plus de controle maladie.
5. Des actions couteuses mais agronomiquement utiles.

Elle n'est pas toujours la plus rentable.

### Optimum economique

C'est la strategie qui cherche le meilleur retour net attendu.

Elle peut recommander moins d'actions que l'optimum agronomique si certaines interventions coutent plus qu'elles ne rapportent.

Par definition, l'optimum economique doit etre la meilleure strategie parmi les options evaluees sur le retour net. Si une autre strategie semble meilleure, il faut verifier les couts, les prix, l'horizon et les calculs.

## 20. Lire les calendriers recommandes

Les recommandations doivent contenir des calendriers pratiques.

### Calendrier d'irrigation

Pour chaque evenement, verifiez :

1. La date.
2. La quantite d'eau.
3. L'unite utilisee.
4. Le volume total si affiche.
5. La raison de l'irrigation.
6. Le cout estime.

Si vous ne pouvez pas irriguer a cette date, utilisez la page What-if pour tester une autre date.

### Calendrier de fertilisation

Pour chaque evenement, verifiez :

1. La date.
2. Le produit.
3. La dose par hectare.
4. La quantite totale.
5. Le cout estime.
6. La raison agronomique.

Verifiez toujours la disponibilite locale et les regles d'application.

### Controle maladie

Pour chaque recommandation maladie, verifiez :

1. La maladie suspectee.
2. La date de detection.
3. Les foyers ou parcelles concernees.
4. Le type d'action : scouting, traitement, pruning, roguing, hygiene, surveillance.
5. Le cout estime.
6. Le gain attendu.
7. L'incertitude.

Ne detruisez pas automatiquement un foyer. Comparez toujours la reduction d'inoculum attendue avec la perte de rendement.

## 21. Telecharger le PDF de recommandations 📄

Le PDF de recommandations est fait pour etre lu et partage.

1. Ouvrez l'onglet Action list ou l'onglet equivalent.
2. Cliquez sur Prepare readable recommendations PDF ou son equivalent en francais.
3. Attendez le spinner de preparation.
4. Cliquez sur Download readable recommendations PDF.
5. Ouvrez le PDF.
6. Verifiez que le logo Scale AG apparait si le rendu PDF l'accepte.
7. Verifiez que les tableaux ne debordent pas.
8. Verifiez que les calendriers sont comprehensibles.
9. Partagez le PDF avec l'agriculteur, le technicien ou le responsable.

Le JSON peut rester disponible, mais il sert surtout a l'archivage technique.

## 22. Utiliser la page What-if 🧪

La page What-if sert a tester une autre strategie que celle recommandee.

Exemple : l'application recommande une irrigation le 15 juillet, mais vous pensez ne pouvoir irriguer que le 18 juillet.

1. Ouvrez la page What-if.
2. Si vous avez deja calcule les recommandations avec les memes parametres, l'application peut reutiliser le plan optimal.
3. Si les parametres ont change, cliquez sur Generate optimized starting plan.
4. Attendez que les calendriers apparaissent.
5. Modifiez une date, une dose ou une action.
6. Supprimez une intervention si vous voulez tester son absence.
7. Lancez le scenario.
8. Comparez le rendement et le retour economique avec la baseline et les optimums.
9. Exportez le rapport de scenario si necessaire.

Un scenario What-if ne doit pas devenir meilleur que l'optimum economique si l'optimum economique a bien evalue la meme possibilite. Si cela arrive, cela signifie souvent que le scenario explore une option non incluse dans l'optimisation de depart, ou qu'un parametre economique doit etre revu.

## 23. Generer le rapport final 🗃️

Le rapport final rassemble les informations importantes.

1. Ouvrez la page Rapport.
2. Verifiez que la configuration et les simulations sont a jour.
3. Pour une culture annuelle, l'horizon du rapport est automatiquement le cycle jusqu'a la recolte.
4. Pour une culture perenne, verifiez l'horizon choisi.
5. Lancez la generation du rapport.
6. Attendez le spinner jusqu'a la fin.
7. Telechargez le PDF.
8. Relisez les sections principales.

Le rapport doit inclure :

1. La description du champ.
2. La culture et la variete.
3. Les donnees sol et meteo utilisees.
4. Les stress abiotiques.
5. Les stress biotiques.
6. Les marges d'erreur.
7. Les recommandations detaillees.
8. Les calendriers d'irrigation et de fertilisation.
9. Les recommandations de controle maladie.
10. La comparaison baseline, optimum agronomique et optimum economique.
11. Le logo Scale AG si le rendu le permet.

## 24. Utiliser la surveillance adaptative 📡

La surveillance adaptative sert a ameliorer l'application avec des mesures terrain.

Vous pouvez ajouter :

1. Rendement observe.
2. Incidence maladie.
3. Donnees de sol.
4. Mesures de croissance.
5. Observations de stress hydrique.
6. Donnees de terrain apres intervention.

Comment l'utiliser :

1. Ouvrez le module de surveillance adaptative.
2. Choisissez le type de mesure.
3. Entrez la date.
4. Entrez la valeur observee.
5. Ajoutez une note si utile.
6. Lancez la calibration si l'option est proposee.
7. Comparez les nouvelles marges d'erreur.

Plus les mesures sont fiables et regulieres, plus les previsions peuvent devenir adaptees au champ.

## 25. Conseils pratiques pour une premiere utilisation

Si vous utilisez l'application pour la premiere fois, suivez ce parcours simple :

1. Choisissez la langue.
2. Choisissez Parcelle unique si vous testez un seul champ.
3. Definissez le champ sur la carte.
4. Selectionnez la culture.
5. Entrez la date de plantation.
6. Gardez la detection automatique du sol si vous n'avez pas d'analyse.
7. Selectionnez une maladie seulement si vous avez une observation.
8. Configurez rapidement l'economie avec des valeurs locales approximatives.
9. Ouvrez le Dashboard.
10. Regardez les stress principaux.
11. Ouvrez Recommandations.
12. Lancez l'optimisation.
13. Telechargez le PDF de recommandations.
14. Testez un scenario What-if seulement si vous voulez modifier le plan.
15. Generez le rapport final.

## 26. Conseils pour une cooperative

Pour une cooperative, prenez plus de temps sur la geographie.

1. Definissez soigneusement le perimetre.
2. Lancez la detection des parcelles.
3. Corrigez les parcelles une par une.
4. Nommez toutes les parcelles.
5. Verifiez que les parcelles ne se chevauchent pas.
6. Configurez la culture commune.
7. Ajustez les dates ou nutriments par parcelle si necessaire.
8. Lancez le dashboard cooperative.
9. Cherchez les parcelles les plus a risque.
10. Lisez les recommandations consolidees.
11. Exportez un rapport clair pour l'equipe terrain.

## 27. Messages, spinners et attentes

Lorsque l'application travaille, elle affiche un spinner ou un message d'attente.

Cela peut arriver pendant :

1. La detection de parcelles.
2. La recuperation de donnees satellite.
3. La detection automatique de sol.
4. La simulation.
5. L'optimisation des recommandations.
6. La preparation d'un PDF.
7. La simulation What-if.

Attendez la fin du traitement avant de changer de page. Si un calcul dure anormalement longtemps, notez la page, le champ et l'action effectuee.

## 28. Erreurs frequentes et quoi faire

### La carte n'est pas au bon endroit

1. Verifiez les coordonnees.
2. Verifiez Nord, Sud, Est, Ouest si vous utilisez le format DMS.
3. Essayez la recherche par lieu.
4. Redessinez le champ manuellement.

### Le champ inclut une route ou une riviere

1. Modifiez le polygone.
2. Supprimez les sommets incorrects.
3. Redessinez la limite.
4. Relancez seulement si necessaire.

### La maladie proposee ne semble pas correcte

1. Verifiez les symptomes sur le terrain.
2. Regardez les autres maladies proposees.
3. Choisissez une validation manuelle si vous etes certain.
4. Gardez une marge de prudence.

### Les recommandations coutent trop cher

1. Verifiez le prix de vente.
2. Verifiez les couts de main-d'oeuvre.
3. Verifiez les prix des intrants.
4. Verifiez l'horizon pour les cultures perennes.
5. Comparez optimum agronomique et optimum economique.
6. Testez une strategie allegee dans What-if.

### Le rapport contient une valeur surprenante

1. Retournez au Dashboard.
2. Verifiez la configuration.
3. Verifiez l'economie.
4. Verifiez les observations maladie.
5. Consultez les marges d'erreur.
6. Ajoutez des donnees de surveillance adaptative si disponibles.

## 29. Comment interpreter les resultats avec prudence

AEF Crop Intelligence est un outil d'aide a la decision. Il ne remplace pas :

1. Une visite de terrain.
2. Un diagnostic phytopathologique confirme.
3. Une analyse de sol locale.
4. La connaissance du producteur.
5. Les contraintes de disponibilite en eau, engrais, main-d'oeuvre et traitement.
6. Les regles locales d'usage des produits phytosanitaires.

Utilisez les resultats comme une base de discussion et de planification.

---

# Part 2 - Step-by-step use in English

## 1. Before you start

AEF Crop Intelligence works best when you have basic field information. You can still use the app with automatic detection when some data are missing.

Prepare, if possible:

1. Field location: GPS center, place name or ability to draw the field on the map.
2. Approximate area.
3. Crop and, if possible, variety.
4. Planting or establishment date.
5. Visible observations: yellowing, lesions, disease foci, water stress, weak growth.
6. Soil information if available: texture, pH, organic matter, nitrogen, phosphorus, potassium and water-holding capacity.
7. Local economic data: sale price, fertilizer costs, water, labour, treatments and services.

You do not need everything. The app provides defaults and automatic estimates, but results are more cautious when data are uncertain.

## 2. Open the app and choose the language 🔐

1. Open AEF Crop Intelligence.
2. On the home page, select the language.
3. Enter your access code.
4. Click the login button.
5. Wait for the workspace to open.

Choose the language at the beginning so pages, alerts and exported reports follow the same choice.

## 3. Choose the working mode

### Single field mode

Use this mode for one field or one continuous plantation block.

It is suitable when:

1. The field is continuous.
2. Crop and variety are the same across the field.
3. You need diagnosis and recommendations for one farm unit.
4. You need irrigation, fertilization and disease-management calendars for that field.

### Cooperative mode 🤝

Use this mode when several small plots are located inside one agricultural perimeter.

It is suitable when:

1. Several farmers are grouped in one area.
2. Plots are small, scattered or irregular.
3. A cooperative or field manager needs a global view.
4. You need to detect, name and correct multiple plots.
5. You need a dashboard and report adapted to multiple plots.

For now, cooperative mode assumes the same crop and variety for all plots, while some settings can still vary by plot.


### Pre-planting assessment mode 🔎

Choose this mode when nothing is planted yet and you want to know whether a selected variety is a good candidate for a field.

This mode is suitable when:

1. You have identified a possible field but the crop is not yet established.
2. You want to compare climate, soil, water needs, fertilizer needs and disease risks before investing.
3. You want the best planting window among the coming months.
4. You want a clear suitability score out of 100.
5. You want a PDF explaining whether planting is recommended, possible with caution or not a priority.

Pre-planting assessment is similar to Single field mode, but it works before planting. For perennial crops, it evaluates only one production cycle, not a multi-year horizon.

## 4. Define geography in Single field mode 🌍

### Method A - GPS coordinates

1. Select the coordinate option.
2. Enter latitude and longitude for the field center.
3. Use decimal coordinates or degree-minute-second-cardinal format.
4. Enter the approximate field area.
5. Generate the field or smart field.
6. Check the proposed polygon on the map.
7. Edit the polygon if it crosses roads, streams, buildings or another crop.

### Method B - Place search

1. Type a known place, village, district or nearby landmark.
2. Run the search.
3. Check the proposed position.
4. Adjust it if needed.
5. Generate the field around that point.
6. Correct the polygon manually if needed.

### Method C - Draw manually

1. Open the drawing tool.
2. Click around the field boundary.
3. Close the polygon.
4. Check the calculated area.
5. Move points until the boundary matches the real field.

Manual drawing is often best when you know the land boundaries well.

## 5. Understand the map

1. Zoom in to inspect the field.
2. Zoom out to check roads, rivers, villages and neighbouring crops.
3. Compare the boundary with field knowledge.
4. Avoid including non-cropped areas.
5. Avoid mixing another crop into the polygon.
6. For perennial crops, make sure the boundary follows the real plantation.

If satellite imagery becomes unavailable at high zoom, the map may switch to a more schematic view. This is normal.

## 6. Define the perimeter in Cooperative mode 🤝

1. Select Cooperative mode.
2. Define the perimeter using coordinates, place search or manual drawing.
3. Check that the perimeter contains the plots to analyse.
4. Run automatic plot detection.
5. Wait for the processing to finish. The app first tries an internal Sentinel-2 and WorldCover guided detector: it analyses vegetated/cultivable pixels inside the perimeter, segments the image and converts segments into editable polygons.
6. If Sentinel-2 is unavailable, too cloudy, not informative enough, or if the perimeter is too large, the app uses a geometric fallback. This fallback creates plausible, irregular, non-overlapping parcel candidates and now keeps a thin visible separation between neighbouring candidates instead of packing them into one artificial block.
7. On the map, plots use contrasting colours inspired by four-colour map reading, plus a white outline. This helps you see narrow field boundaries even when crop cover looks continuous.
8. The app also shows detected cultivated area, unassigned/non-cultivated area and cultivated fraction. A large unassigned area is not automatically an error: it may be roads, drains, buildings, water, fallow land or spaces without crop cover.
9. Read the detection method, mean confidence and estimated boundary precision. Low precision means you must edit the polygons carefully and, when enabled, use precomputed FTW boundaries as a free fallback.
10. Review all detected plots on the map.
11. Delete false plots.
12. Redraw inaccurate plots.
13. Add missing plots with the polygon tool.
14. Give each plot a clear name.
15. Save the configuration.

Detected plots should not overlap. They do not have to be glued together: a thin readable boundary between neighbouring plots is normal and should be preserved. The app no longer tries to fill the whole perimeter; large gaps are allowed, but you should check that they are not missed plots. Correct any overlap before continuing.

## 7. Name cooperative plots

Use clear plot names to avoid confusion.

1. Keep names short.
2. Avoid duplicate names.
3. Include a useful reference: farmer, block, number or location.
4. Check that the name appears in tables and maps.
5. Use the same names in field notes.

Plot names are saved in the configuration JSON.

## 8. Configure crop and variety

1. Open the crop or cropping-system section.
2. Select the crop.
3. Select the variety when available.
4. Enter planting or establishment date.
5. For annual crops, the app automatically uses the expected harvest date as horizon.
6. For perennial crops, the app may use several years because multiple harvest periods can occur.
7. Review crop-cycle and yield information.

If you do not know the exact variety, select the closest one and interpret results cautiously.

## 9. Annual and perennial crops

Annual crops have one main cycle. The analysis horizon runs from planting to expected harvest. You do not need to select years.

Perennial crops remain productive over several years. The economic horizon can be configured because revenue and costs may span several harvest periods. Heavy actions such as severe pruning or tree removal can affect future harvests.

## 10. Configure disease or biotic stress

### Automatic detection

1. Use automatic detection if you do not know the disease.
2. The app analyses available canopy and field signals.
3. It may suggest one likely disease or several options.
4. Validate the most plausible option if field observations support it.
5. Keep uncertainty in mind.

Automatic detection guides scouting; it does not replace field confirmation.

### Manual disease selection

1. Select the disease.
2. Enter observation date.
3. Place disease foci on the map if available.
4. Estimate affected plants or severity.
5. Add several foci if the disease appears in multiple places.
6. Check that all foci are inside the field.

### Cooperative mode

1. Display the plot map.
2. Select the affected plot.
3. Add or correct disease foci.
4. Repeat for other plots if needed.
5. Keep map entries consistent with field scouting.

## 11. Roguing, pruning and disease interventions

Removal is never automatic.

The app must compare:

1. Expected benefit: reduced inoculum and lower future spread.
2. Agronomic cost: loss of productive plants, stand density or canopy.

For annual crops, plant removal can be useful for small, dangerous foci, but excessive removal can reduce yield more than the disease.

For perennial crops, tree removal or severe pruning can reduce production over several harvests. Confirm the disease before removing productive plants.

## 12. Configure soil

### Automatic soil detection

1. Use automatic detection when you lack a soil test.
2. The app estimates soil properties from available geographic datasets.
3. Check whether values seem plausible.
4. Treat them as a starting point.

### Manual configuration

1. Enter texture if known.
2. Enter pH.
3. Enter organic matter.
4. Enter nutrient levels if available.
5. Enter initial water or moisture if available.
6. Check units carefully.

### Expert configuration

Only change advanced parameters if you understand them. Otherwise keep defaults.

### Cooperative mode soil

1. Keep the plot map visible.
2. Check which plot you are editing.
3. Enter initial nutrients by plot if available.
4. Enter land-use history by plot.
5. Use plot names to avoid mistakes.

## 13. Configure economics

Economics allow the app to compare strong agronomic action with profitable action.

Enter:

1. Currency.
2. Sale price.
3. Price source.
4. Fertilizer prices.
5. Water or irrigation cost.
6. Labour cost per day and per hectare when requested.
7. Treatment costs.
8. Replacement plant cost.
9. Scouting cost.
10. Pruning or roguing cost if relevant.

If you change the price source, check that the displayed assumptions make sense.

## 14. Save and reload configuration 💾

### Save

1. Finish field configuration.
2. Download the JSON configuration.
3. Store it with a clear name.

### Reload

1. Open the app.
2. Upload the configuration JSON.
3. Check map, crop, soil, economics and disease settings.
4. Update anything that changed.

JSON is useful for technical storage. PDF is easier for field communication.

## 15. Use the Dashboard 🛰️

1. Complete configuration.
2. Open Dashboard.
3. Wait for calculations.
4. Select the date you want to inspect.
5. Read yield forecast, water stress, nutrient stress, disease stress and uncertainty.
6. Check maps when available.
7. Compare outputs with field knowledge.

The dashboard estimates field status; it does not provide certainty.

## 16. Understand reality check

Reality check compares past real observations with the simulation.

It only makes sense between planting date and the current observation date. It should not compare the future with satellite observations that do not exist.

Use it to see whether the model follows observed field development.

## 17. Read uncertainty margins

Large uncertainty can come from missing soil data, uncertain disease identity, rough cost estimates or few field observations.

Smaller uncertainty usually means better local data and adaptive surveillance updates.

Always read ranges, not only central values.


## 17A. Use Pre-planting assessment 🔎

Pre-planting assessment helps decide before planting. It starts from a candidate field and the variety you are considering.

Steps:

1. Choose Pre-planting assessment on the home screen.
2. Name the candidate field.
3. Enter the GPS centre or position the field on the map.
4. Enter the approximate area.
5. Generate the candidate parcel if you need a simple boundary.
6. Optimize the candidate parcel against satellite land cover if you want the app to search for a more plausible cultivable area around the centre.
7. Draw or correct the polygon manually when needed.
8. Select crop and variety.
9. Check whether the crop is annual or perennial. For perennials, the assessment remains limited to one cycle.
10. Enter the earliest acceptable planting date.
11. Configure soil manually or use automatic soil detection.
12. Run the pre-assessment.
13. Read the suitability score out of 100.
14. Read the proposed best planting date.
15. Review irrigation and fertilization calendars for the cycle.
16. Review disease risks from the literature-based disease pressure file.
17. Download the pre-assessment PDF.

The score combines climate fit, water feasibility, soil and nutrients, disease pressure, planting window and data confidence. A high score does not replace a field visit, soil test or local disease surveillance. It means the field appears favourable according to available data.

## 18. Open Recommendations 🧭

1. Open Recommendations.
2. Review the setup.
3. Annual crops do not require a year horizon.
4. Perennial crops may require an economic horizon.
5. Click the optimization button.
6. Wait for the calculation.
7. Read each result tab.

Optimization should start only when you click the button.

## 19. Understand the three strategies

### Baseline / no action

This is the expected result if no additional management is applied. It still has production, costs and net return. Only the incremental gain versus itself is zero.

### Agronomic optimum

This strategy maximizes stress reduction and production. It can be expensive and is not always the most profitable.

### Economic optimum

This strategy maximizes expected net return among evaluated options. It may keep fewer actions than the agronomic optimum when costs are high.

## 20. Read recommended calendars

### Irrigation

Check date, water amount, total volume, reason and estimated cost.

### Fertilization

Check date, product, rate per hectare, total quantity, cost and agronomic rationale.

### Disease control

Check suspected disease, detection date, affected plots, action type, expected benefit, cost and uncertainty.

Do not remove disease foci automatically. Compare inoculum reduction with yield loss.

## 21. Download the recommendations PDF 📄

1. Open the Action list or equivalent tab.
2. Prepare the readable recommendations PDF.
3. Wait for the spinner.
4. Download the PDF.
5. Open it.
6. Check tables, calendars and disease recommendations.
7. Share it with the farmer, technician or manager.

JSON can remain available as a technical export.

## 22. Use What-if 🧪

1. Open What-if.
2. If Recommendations were already calculated with the same settings, the app can reuse them.
3. If settings changed, generate the starting plan.
4. Edit irrigation dates, amounts, fertilization or disease control.
5. Run the scenario.
6. Compare yield and economic return.
7. Export the scenario report if needed.

What-if is useful when real constraints prevent following the exact recommended calendar.

## 23. Generate the final report 🗃️

1. Open Report.
2. Check that simulations are current.
3. For annual crops, the report horizon follows the crop cycle.
4. For perennial crops, check the selected horizon.
5. Generate the report.
6. Wait until the PDF is ready.
7. Download and review it.

The final report should include field description, crop, soil, weather, stresses, uncertainty, detailed recommendations, calendars, disease control, economic comparison and Scale AG signature when available.

## 24. Use adaptive surveillance 📡

1. Open adaptive surveillance.
2. Choose measurement type.
3. Enter date.
4. Enter observed value.
5. Add notes if useful.
6. Run calibration if available.
7. Review updated uncertainty.

Regular reliable field measurements help the app become better adapted to the field.

## 25. First-use path

For a first test:

1. Choose language.
2. Choose Single field.
3. Draw or generate the field.
4. Select crop.
5. Enter planting date.
6. Use automatic soil detection if no soil test exists.
7. Add disease only if observed.
8. Enter simple economics.
9. Open Dashboard.
10. Read main stresses.
11. Open Recommendations.
12. Run optimization.
13. Download recommendations PDF.
14. Use What-if only if you need to change the plan.
15. Generate final report.

## 26. Cooperative path

1. Define cooperative perimeter.
2. Enter the expected number of individual plots when the cooperative knows it; keep 0 only when it is unknown.
3. Detect plots. AEF uses the expected count to tune Sentinel-2 segmentation and avoid returning a misleading excess of polygons.
4. Correct plot boundaries.
5. Name every plot.
6. Check that plots do not overlap.
7. Configure shared crop and variety.
8. Adjust plot-level dates or nutrients when needed.
9. Run cooperative dashboard.
10. Identify highest-risk plots.
11. Read consolidated recommendations.
12. Export the final report.

## 27. Spinners and waiting messages

Wait when the app is detecting plots, loading satellite data, estimating soil, simulating, optimizing, preparing PDFs or running What-if.

Do not change pages during long calculations unless the app has clearly finished.

## 28. Common issues

### Wrong map position

Check coordinates, DMS cardinal directions, place search and manual drawing.

### Boundary includes road or stream

Edit the polygon before continuing.

### Disease looks wrong

Check field symptoms, validate manually or keep uncertainty high.

### Recommendations are too expensive

Check sale price, labour, input costs, perennial horizon and economic optimum. Use What-if to test a lighter plan.

### A report value is surprising

Check configuration, economics, disease observations, uncertainty and adaptive surveillance data.

## 29. Use results cautiously

AEF Crop Intelligence supports decisions. It does not replace field visits, confirmed disease diagnosis, local soil analysis, farmer knowledge, local water/input/labour constraints or local phytosanitary rules.

Use the results as a structured basis for discussion, planning and follow-up.


### Mise à jour du mode Pré-évaluation - limites automatiques plus prudentes 🔎

Dans le mode **Pré-évaluation**, le bouton **Optimiser la parcelle candidate avec la couverture satellite** applique maintenant un contrôle plus strict avant de dessiner automatiquement une limite. Si la meilleure zone détectée contient trop de bâti, d’eau, de zone humide ou de couverture inconnue, AEF n’applique pas ce polygone automatiquement. L’application affiche alors les raisons du rejet et vous demande de déplacer le centre ou de dessiner manuellement la limite sur la carte satellite.

Les dates candidates de plantation sont affichées au format explicite **AAAA-MM-JJ**. Par exemple, `2026-07-15` signifie 15 juillet 2026. Le résultat se termine aussi par une **recommandation finale en paragraphe**, qui résume le score, la date conseillée, le risque maladie principal, la qualité des données de sol et les validations à faire avant d’investir.

### Pre-planting update - more cautious automatic boundaries 🔎

In **Pre-planting assessment**, the **Optimize candidate parcel against satellite land cover** button now applies a stricter check before accepting an automatic boundary. If the best detected area still contains too much built-up cover, water, wetland, or unknown cover, AEF does not apply that polygon automatically. The app explains why the candidate was rejected and asks you to move the centre or draw the parcel manually on the satellite map.

Planting date candidates use the explicit **YYYY-MM-DD** format. For example, `2026-07-15` means 15 July 2026. The result also ends with a **final recommendation paragraph**, summarizing the score, recommended date, main disease risk, soil-data quality and the checks to complete before investing.


### Cooperative plot-count guidance 🤝

When a cooperative already knows how many farmer plots are inside the perimeter, enter that number before automatic plot detection. AEF uses it as a strong but cautious prior: Sentinel-2 segmentation and the geometric fallback both target that non-overlapping count while still requiring map validation. If detected and expected counts differ, adjust the expected count or edit the polygons before continuing.
