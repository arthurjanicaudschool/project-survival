# Traitement des 40 constats — politique survival-v5

L'objectif est de donner aux agents de meilleurs moyens et de corriger les erreurs
techniques. Aucun changement ne garantit un rendement positif, une disponibilité
de 100 % ou une diversité d'intelligence entre dix instances du même modèle.
L'expérience en cours conserve son START, sa fin, ses portefeuilles et son journal.
Chaque changement de règles est enregistré avec une valorisation de référence.

Le rapport initial figure dans [AUDIT-2026-10-13.md](AUDIT-2026-10-13.md).
« Corrigé » désigne une modification du système vérifiable ; les limites indiquées
restent réelles et ne sont pas présentées comme des problèmes résolus.

| Point | Traitement livré | Limite ou convention restante |
|---|---|---|
| 1 | NAV/ROI nuls si cotation inconnue ; bornes séparées ; agent non classé | Inconnu ne signifie ni zéro ni perte |
| 2 | État CLOSING récupérable ; aucun nouveau trade après la fin ; rapport définitif seulement si valorisation complète | Une cotation historique inexistante ne peut être recréée |
| 3 | Rafraîchissement des positions avant chaque analyse ; rafraîchissement des trades après réflexion ; valorisation commune finale | Les analyses séquentielles ne se produisent pas à la même seconde |
| 4 | Minimum réel également appliqué à la valeur liquidable ; résidus effectivement invendables à zéro cash liquidable, distincts des cotations inconnues | Leur valeur économique future reste bornée et peut recevoir un payout ; aucun fill ni perte réalisée inventé |
| 5 | Dernière observation antérieure ou égale à la fin, âge maximum 15 minutes ; aucun prix futur | Convention annoncée, pas reconstruction d'un carnet exact à la seconde |
| 6 | Extraction HTML structurée ; suppression des scripts ; texte vide/inutilisable en erreur | Pertinence sémantique encore évaluée par l'agent |
| 7 | Flux institutionnels directs, puis Bing RSS, GDELT et Google News avec erreurs visibles | Recherche gratuite sans garantie de disponibilité ni d'exhaustivité |
| 8 | Données publiques structurées Coinbase, BLS, NOAA et XTracker avec sources/horodatages | Coinbase peut être un proxy ; NOAA décrit les tempêtes actives ; panne XTracker visible |
| 9 | 4 tours × 4 outils, budget de 150 secondes, cible de 3 candidats dynamiques/2 standards ; compteurs visibles | La cible n'autorise ni données inventées ni appels illimités |
| 10 | Quatre tris de découverte et catégories alternées ; 24 marchés initiaux ; recherche hors catalogue inchangée | La liste initiale reste bornée ; l'agent peut chercher ailleurs |
| 11 | Curseur interne préservant tous les marchés d'une page déroulée | Pagination liée à la requête ; testé sur 135 marchés |
| 12 | Mémoire des pistes et erreurs ; surveillance des positions indépendante des appels IA ; cache partagé persistant | L'agent choisit encore ses outils ; browse n'est pas forcé |
| 13 | Historique demandé à 5 minutes sur 8 heures ; traits calculés en Python | Disponibilité et granularité effective dépendent du fournisseur |
| 14 | Spread, minimum frais inclus, momentum, variation, volatilité et scénarios crypto calculés | Pas de modèle fondamental/sentiment universel calibré ; scénarios explicitement illustratifs |
| 15 | Prompts distincts, mêmes observations initiales, métrique de recouvrement des marchés dans le rapport | Même modèle de base ; la diversité et la supériorité ne sont pas garanties |
| 16 | Affirmations rattachées à des citations exactes de pages lisibles ; contrôle après corrections JSON | Une citation présente ne prouve pas automatiquement l'implication logique ou la causalité |
| 17 | Réflexion possible sur événement après 10 min/30 min, avec plafonds UTC inchangés 12/4 | Un quota quotidien épuisé n'est pas contourné |
| 18 | stop_bid/take_profit_bid/exit_at choisis par l'agent et surveillés chaque cycle | Stops observés périodiquement ; prix d'exécution non garanti |
| 19 | Plan de 1 à 4 actions ordonnées ; cash d'une vente disponible pour l'achat suivant | Chaque action reste contrôlée sur cash et profondeur ; aucune atomicité de marché réel |
| 20 | Thèse PRICE_MOVE avec cible, horizon et prix maximum, sans fausse probabilité de résolution | Edge de scénario distinct d'une espérance mathématique calibrée |
| 21 | Exploration initiale toujours étiquetée et comptée séparément ; aucune obligation répétée après le premier fill | Règle précédemment demandée par le propriétaire conservée ; elle peut perdre de l'argent fictif |
| 22 | Un prudent à 10 EUR peut proposer un minimum réel jusqu'à 45 % de sa NAV si les autres limites le permettent | Aucune mise augmentée automatiquement ; minimums/solde ne sont jamais supprimés |
| 23 | Expositions économiques communes et corrélations de variations sur timestamps communs (au moins 6) | Petit échantillon ; corrélation de prix différente de dépendance des résolutions |
| 24 | Copie indépendante du même catalogue initial ; découvertes d'un agent non injectées chez les suivants dans le cycle | Données réutilisables au prochain cycle ; moments de réflexion différents |
| 25 | max_buy_price/min_sell_price choisis par l'agent ; borne respectée après rafraîchissement | Les bornes sont arrondies vers le côté protecteur du tick |
| 26 | sell_quantity/close_position ; règles de sortie attachées à chaque position | Les anciens titres fractionnaires peuvent laisser une poussière réelle |
| 27 | Edge SELL = produit net par titre moins valeur estimée de conservation | Aucun edge numérique affiché pour une probabilité non estimée |
| 28 | Minimum vérifié à la soumission ; fill partiel sous minimum admis ; précision conservatrice de taille à 2 décimales | Convention FAK limit papier ; pas de prétention de signature/matching identiques au SDK |
| 29 | 40 niveaux d'exécution ; consommation de la profondeur entre actions d'un même portefeuille | Portefeuilles contrefactuels indépendants ; aucune confirmation d'exécution réelle |
| 30 | Marchés à délai ≤ 30 secondes : attente puis nouvelle observation avant trade | Maker au repos et files d'attente restent exclus, faute de preuve suffisante de fill |
| 31 | Métadonnées et frais revalidés avant le trade ; aucun taux fixe arbitraire | Frais inconnus = marché indisponible |
| 32 | « Sorties positives », nombre de valeurs manquantes, volatilité non annualisée, exposition, ROI/drawdown | Les drawdowns entre observations restent inconnus ; pas de faux Sharpe sur sept jours |
| 33 | Identifiant de chaque hypothèse ; références dans les achats suivants ; résultats associés calculés | Mémoire contextuelle, pas réentraînement ni preuve d'amélioration causale |
| 34 | Souvenirs pertinents et récents ; mémoire de recherche ; calibration de toutes prévisions observées résolues, y compris WAIT | Pas de faux trades contrefactuels ; marchés suivis bornés et observations incomplètes signalées |
| 35 | Verrou de session sans transaction HTTP longue ; tâche READY persistante ; transactions financières courtes ; reprise sous l'identité originale | Une coupure avant réception/persistance de la réponse reste une requête au coût incertain |
| 36 | Réparation JSON bornée ; reprise technique après 15 min ; état technique distinct de WAIT | Échecs comptés dans les quotas ; aucune boucle de retry illimitée |
| 37 | Cron GitHub + secours Supabase + horloge indépendante Cloudflare ; traces du déclencheur | Le moteur dépend encore des runners GitHub, du stockage Supabase et d'Azure |
| 38 | Plafonds autorisés 100 EUR total/20 EUR par jour ; réservation avant chaque requête, mesure indépendante, cache/contexte bornés, aucun retry Azure caché | Tarifs conditionnels fournis par le propriétaire ; facturation Azure et quotas du compte font foi |
| 39 | Rôle DB limité, RLS, comptabilité réconciliée à chaque agent, erreurs partielles, statut Realtime/secours 60s, catégories inférées identifiées, régressions, sauvegarde quotidienne, projection bornée | Quotas egress/Actions partagés et trafic à surveiller ; exports ≠ dump complet avec Vault |
| 40 | Égalités explicites, agents non valorisables hors classement, référence cash, phases de politique, exploration/exposition/diversité dans le rapport | Deux agents par stratégie, sept jours et changement de règles ne prouvent pas une performance future |

## Coûts et fréquence

Les plafonds de sessions restent **72/jour, 504/semaine** au maximum, avant les
filtres. Les événements utilisent ces mêmes sessions, sans quota supplémentaire.
Une session v5 utilise au plus 4 requêtes de recherche + 1 décision + 1 réparation
éventuelle + 1 correction de participation éventuelle. La réparation a un budget
de sortie doublé. Les outils publics ne sont pas des appels LLM supplémentaires.

| Paramètre | Avant v5 | V5 |
|---|---:|---:|
| Tours / outils par tour | 3 / 3 | 4 / 4 |
| Budget normal de sortie par requête | 1 600 tokens | 2 600 tokens |
| Sessions hebdomadaires maximum | 504 | 504 |
| Contexte | Compactage partiel | JSON préservé et plafond contrôlé |
| Budget global | Aucun contrôle global | 100 EUR total, 20 EUR/jour UTC |
| Échecs après appel | Coût parfois absent du journal | Réservation prudente conservée |

Le prix de la nouvelle politique doit être **mesuré après déploiement**. Multiplier
aveuglément les anciens euros par les nouveaux tours ne serait pas une prévision
fiable. `cost-report` produit les quatre offres conditionnelles avec cache lu/écrit
quand ces compteurs sont disponibles. Une reprise n'achète pas deux fois la même
décision prête. Le plafond logiciel est une estimation conservatrice, pas un
plafond contractuel de facturation Azure. Les anciennes requêtes non mesurées ne
peuvent pas être reconstituées.

## Exploitation

`python -m survival.cli health`, `cost-report`, `quota-check`, `research-check` et
`api-check` exposent les preuves de fonctionnement. Le workflow de sauvegarde
exporte chaque jour à 03:43 UTC, conserve son artifact 14 jours, et peut être lancé
manuellement. La restauration doit s'effectuer dans une base distincte, jamais
par écrasement de la compétition active.
