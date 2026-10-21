# PROJECT SURVIVAL — Phase 2

## Ce qui change

L'objectif est de prévoir des événements, pas de gagner à la revente. Chacun des
dix agents reçoit 100 EUR fictifs au START. A1/A2 : politique ; A3/A4 : sport ;
A5/A6 : météo ; A7/A8 : crypto ; A9/A10 : économie. Les agents d'une paire ont
la même méthode et le même capital, mais des portefeuilles, recherches, décisions
et mémoires séparés. Aucun résultat de la phase 1 ne prouve qu'une mentalité est
optimale : le choix commun est **libre et raisonné**, avec des probabilités
explicites, des sources vérifiables et une mise décidée par l'agent.

Une mise typique de 10 à 25 EUR est conseillée dans le prompt, sans minimum
artificiel ni plafond discrétionnaire. L'agent peut choisir une autre mise et
plusieurs événements à la fois. Les contraintes réelles restent obligatoires :
argent disponible, minimum du marché, prix limite, tick, profondeur observée,
frais propres au marché, ancienneté des données. Pas d'emprunt, de pari forcé,
de facture ou de transaction Polymarket réelle.

## Contrat d'un pari

Le moteur accepte seulement BUY et WAIT pour la phase 2. Le JSON de génération
est restreint aussi ; le contrôle Python reste indépendant du prompt. Un BUY
doit porter sur le domaine assigné, avoir une probabilité estimée et une thèse de
résolution. SELL, PRICE_MOVE, stops, take-profit, exploration obligatoire,
changement de côté et nouveau pari sur le même marché sont refusés. Le montant
effectivement exécuté est retiré du compte et bloqué. Un ordre partiel conserve
seulement la partie réellement simulée contre le carnet ; aucun complément
automatique n'est inventé.

Les événements doivent finir entre maintenant et **fin du défi moins 24 h**.
Le moteur exige règles, source de résolution et date disponibles. L'agent doit
examiner les règles et éviter les événements reportables ou à calendrier ambigu.
La catégorie provient de la taxonomie du fournisseur, ou d'une classification
explicite des questions/tags ; cette dernière peut être imparfaite. Les marchés
non classés sont exclus. Une date de fin n'est pas une garantie de résolution.

Après la limite des paris, aucune nouvelle réflexion ni mise. Les résultats
continuent d'être collectés. Après 168 h, s'il manque une résolution, le statut
est CLOSING, le classement reste provisoire et la mise reste visible en attente.
FINISHED intervient seulement quand tous les paris ont des résultats officiels.
Aucune vente forcée, abandon ou fausse résolution pour rendre le tableau vert.

## Lire le dashboard

- **Argent disponible** : ce que les agents peuvent encore miser.
- **Argent engagé** : coût des paris non résolus, frais inclus. Ce n'est ni une
  perte constatée ni une valeur de revente.
- **Gains/pertes confirmés** : montants récupérés après résolution moins mises
  et frais correspondants. Les paris non résolus n'y figurent pas.
- **Résultat en attente** : le choix est verrouillé et attend le fournisseur.
- **Classement provisoire** : gains confirmés / capital initial ; les mises en
  attente peuvent encore le modifier. Les égalités ne créent pas de faux gagnant.

Chaque carte de pari affiche agent, somme, choix Oui/Non, question, raisonnement,
sources, frais inclus, date de l'événement et montant récupéré à la résolution.
L'historique technique complet reste en base/export ; aucun JSON brut n'est
affiché dans la navigation habituelle. `/?phase=1` ouvre l'archive inchangée.
`/?mode=demo` est une démonstration synthétique séparée, jamais une expérience.

## Mémoire et apprentissage

Avant chaque décision sont fournis : dernier résumé, douze résumés d'actions,
résultats officiels récents et pertinents, mises ouvertes, calibrage des
probabilités et leçons précédentes. L'agent doit indiquer ce qui change dans son
raisonnement, ou expliquer l'absence de précédent pertinent. Les leçons sont
rattachées à des épisodes réellement enregistrés ; les références inventées sont
écartées. Les résultats sont recalculés depuis le journal financier complet, pas
uniquement les cartes visibles. C'est une adaptation par mémoire, pas un
réentraînement des poids, ni une promesse d'amélioration à chaque pari.

## Réduire le coût IA

Le déploiement Azure existant est conservé. Aucune migration vers un modèle moins
bon sans évaluation. Les recherches sont mises en cache et partagées ; les
portefeuilles et décisions restent indépendants. Plus d'analyse de revente ni de
réaction LLM aux variations des positions bloquées. Les historiques de prix ne
sont pas collectés automatiquement pour les paris de phase 2.

| Mesure | Phase 1 observée | Phase 2 prévue |
|---|---:|---:|
| Sessions réussies | 1 313 | environ 180 sur les 6 jours ouverts aux mises |
| Requêtes IA mesurées dans l'export | 6 864 | habituellement jusqu'à 720, hors reprises/réparations |
| Fréquence normale | signaux + recherches périodiques | une recherche / 8 h / agent disposant de cash |
| Tours de recherche par session | jusqu'à 4 | jusqu'à 3 |
| Contexte de recherche | 120 000 caractères | 50 000 caractères |
| Reventes | 48 ordres exécutés | 0 |

180 = 10 agents × 3 sessions/jour × 6 jours. Les incidents peuvent déclencher des
reprises après une heure ; une réparation JSON peut ajouter un appel. Ce sont
des ordres de grandeur de fonctionnement normal, **pas des quotas quotidiens ou
un plafond de dépenses**. Les anciens blocages par estimation de crédits restent
désactivés conformément à la demande. Les tokens réellement consommés restent
mesurés par requête. Les économies en euros dépendront du contexte, du cache et
de l'offre Azure ; seul Azure fait foi pour la facture. On réduit les tâches
inutiles, mais une performance identique ou meilleure ne peut pas être garantie.

## Audit des frais de phase 1

Sur l'export final conservé localement, les frais des 108 ordres exécutés totalisent
**6,71817 unités de cotation = 6,00856 EUR** au taux figé de 1,1181. Dont 3,68631
à l'achat et 3,03186 à la vente. Les frais de chaque fill correspondent à la
formule, au taux et à l'exposant enregistrés, avec arrondi à cinq décimales.
Cela vérifie la cohérence du calcul, pas une facture réelle (toute l'expérience
était fictive), ni une validation indépendante des taux historiques.

La documentation actuelle décrit `quantité × taux × prix × (1-prix)` pour les
frais taker et des taux par marché. Le champ taux n'est pas un pourcentage à
appliquer directement à la mise. Le simulateur lit les paramètres du marché et
ne remplace pas les taux par une moyenne par catégorie. Le spread est un écart
de prix, pas une ligne supplémentaire de frais ; le coût Azure est distinct.
En phase 2 : frais à l'achat, aucune revente, règlement officiel sans frais de
trading ajoutés. Aucun rebate maker ou taker n'est crédité sans preuve.

Sources consultées le 22 octobre 2026 :
- https://docs.polymarket.com/trading/fees
- https://docs.polymarket.com/market-data/market-details
- https://docs.polymarket.com/trading/positions/manage
- https://developers.openai.com/api/docs/guides/structured-outputs

## Déploiement et départ explicite

1. Appliquer les migrations, dont `005_phase2_event_bets.sql`, avec le compte
   d'administration local ; conserver le rôle limité pour les workflows.
2. `python -m survival.cli prepare-phase2 --experiment survival-002` prépare les
   dix profils en statut READY, sans taux fictivement actuel, sans financement
   du journal, sans collecte de marchés ni appel Azure.
3. Dans les variables GitHub du dépôt, `EXPERIMENT_ID=survival-002` dirige cycles
   planifiés et sauvegardes vers la phase 2. La page principale utilise cet ID ;
   l'archive force toujours `survival-001`.
4. Installer/reconfigurer les watchdogs sur `survival-002`. READY n'est jamais
   considéré comme un moteur en retard. Les secours déclenchent GitHub ; ils ne
   constituent pas un moteur de calcul indépendant si GitHub est indisponible.
5. Vérifier le dashboard réel, la démonstration et les tests. **Ne pas lancer
   START lors du déploiement.**
6. Au moment choisi : GitHub Actions → SURVIVAL cycles → Run workflow → action
   `start`, expérience `survival-002`. Ou commande ci-dessous. Le taux EUR/USD
   horodaté et le début des 168 h sont enregistrés seulement à cet instant.

```powershell
python -m survival.cli start --experiment survival-002
python -m survival.cli cycle --experiment survival-002
python -m survival.cli health --experiment survival-002
python -m survival.cli export --experiment survival-002 --output exports/phase2
```

Les sauvegardes quotidiennes GitHub sont retenues 14 jours. L'export contient
JSON et CSV ainsi que l'intégralité du journal append-only. Conserver aussi
l'archive de la phase 1. Les secrets restent dans `.env`, les secrets GitHub et
le Vault ; aucun token n'est requis dans le navigateur.

## Vérifications locales

```powershell
python -m pytest -q
python -m survival.cli demo-phase2
python -m survival.cli api-check
cd frontend
npm run build
```

Le test API requiert un accès public autorisé ; aucune restriction géographique
n'est contournée. Les tests PostgreSQL utilisent exclusivement une base de test
jetable via TEST_DATABASE_URL. Ils ne doivent jamais injecter de fixtures dans
la base réelle de la compétition. GitHub Actions reste un service gratuit à
exécution approximative, sans garantie de ponctualité ou de disponibilité.
