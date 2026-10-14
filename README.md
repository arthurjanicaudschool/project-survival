# PROJECT SURVIVAL

Politique **survival-v5.4** : à la demande du propriétaire, les plafonds quotidiens
de sessions et les blocages par estimation financière sont désactivés. Les anciens
12/4 et 100/20 restent des réglages historiques inactifs ; ils ne bloquent aucun
appel. Les intervalles de découverte (2 h dynamiques/6 h standards) et événements
(10/30 min), la mesure des tokens, l'idempotence et les contraintes d'exécution
réalistes restent actifs. Les crédits consommés peuvent dépasser les anciens
montants ; les restrictions imposées par les fournisseurs restent applicables.
Les sections suivantes conservent l'historique v5, à lire avec ce changement.

**10 AI Agents. 7 Days. One Winner.**

Dix portefeuilles indépendants de paper trading, données publiques Polymarket,
Azure OpenAI, PostgreSQL/Supabase, dashboard React. Aucun wallet ni ordre réel.
Le PC peut être éteint : GitHub exécute les cycles. Politique **survival-v5**.
[Traitement des 40 constats](docs/REMEDIATION.md) et [audit initial](docs/AUDIT-2026-10-13.md).
[Bilan de livraison et preuves](docs/LIVRAISON-V5.md).

## Installation et commandes

Python 3.11+, Node 22.12+, PowerShell depuis la racine :

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e '.[test]'
Copy-Item .env.example .env
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m survival.cli demo
Set-Location frontend
npm ci
npm run dev
```

Ouvrir http://127.0.0.1:5173/?mode=demo. Les fixtures utilisent une base SQLite
isolée ; elles ne servent jamais de secours aux données réelles.

```powershell
# Depuis la racine ; DATABASE_URL désigne le compte opérationnel limité.
.venv/Scripts/python -m survival.cli api-check
.venv/Scripts/python -m survival.cli research-check
.venv/Scripts/python -m survival.cli migrate
.venv/Scripts/python -m survival.cli start
.venv/Scripts/python -m survival.cli cycle --cycle-id manual-unique-id
.venv/Scripts/python -m survival.cli health
.venv/Scripts/python -m survival.cli cost-report
.venv/Scripts/python -m survival.cli quota-check
.venv/Scripts/python -m survival.cli export --output exports/week-01
```

`migrate` utilise DATABASE_ADMIN_URL quand présent. START est explicite, fixe
end_at à START + 168 heures et refuse de réinitialiser un identifiant existant.
Les mises à jour conservent portefeuilles et journal financier.

## Agents et liberté

| Stratégie | 10 EUR | 50 EUR | Réflexions maximum/jour UTC |
|---|---|---|---:|
| HUNTER | A1 | A6 | 12 |
| SPRINTER | A2 | A7 | 12 |
| ANALYST | A3 | A8 | 4 |
| VALUE | A4 | A9 | 4 |
| CONTRARIAN | A5 | A10 | 4 |

Prompts, portefeuilles et mémoires distincts. A1/A6 n'ont pas de prudence imposée.
Les autres limites sont configurables dans config/settings.json. Cash négatif,
emprunt et suppression des contraintes réelles sont interdits. Les quatre agents
dynamiques ont une obligation initiale de participation précédemment autorisée :
[règles d'exploration](docs/PARTICIPATION.md). Après le premier fill, aucun nouvel
investissement n'est forcé. WAIT reste une décision légitime.

Un agent peut rechercher n'importe quel marché public ; les 24 marchés initiaux
ne sont pas une liste blanche. Quatre tours de recherche et quatre outils par tour,
avec un budget de temps, permettent recherche/pagination/inspection, actualités,
lecture de pages et données structurées gratuites. Les pannes restent visibles.

Une réflexion produit un plan JSON de 1 à 4 actions validé par Pydantic : vendre
puis acheter, choisir ses prix maximum/minimum et ses seuils de sortie surveillés
chaque cycle. Une thèse PRICE_MOVE est distincte d'une probabilité de résolution.
Les leçons sont des hypothèses contextualisées, reliées aux résultats observés ;
le modèle n'est pas réentraîné.

## Simulation et comptabilité

SDK unifié officiel polymarket-client 0.13.0, PublicClient uniquement, identifiants
v1/v2. Calculs Decimal. Convention conservatrice FAK limit : tailles à deux
décimales, frais à cinq, minimums de soumission, tick et profondeur observée.
Un fill partiel peut être inférieur au minimum de soumission. Quarante niveaux
sont conservés pour l'exécution ; un portefeuille ne réutilise pas une profondeur
déjà consommée par une action du même plan.

Frais/métadonnées et carnets revalidés avant trade. Un délai de matching jusqu'à
30 secondes impose une nouvelle observation après attente. Maker au repos exclu.
Le simulateur ne confirme pas un matching réel et ne modélise pas toute la
concurrence, les annulations et la latence.

Valorisation au bid net immédiatement liquidable. Cotation manquante/périmée :
NAV/ROI inconnus, bornes séparées, agent non classé. Un résidu sous un minimum ou
une précision effectivement observés apporte zéro cash liquidable ; sa valeur
économique future n'est pas supposée nulle et le résidu reste signalé.
Aucun prix inventé. Les résolutions exigent les payouts officiels. Le taux BCE
EUR/USD obtenu au START reste figé ; aucun gain de change attribué au trading.
La convention fictive pUSD/USD est affichée.

À la fin : arrêt des décisions, dernière observation antérieure ou égale à la
limite, âge maximum 15 minutes. Sinon CLOSING, sans prix futur ni faux gagnant.
Le rapport distingue égalités, ROI/bénéfice absolu, exploration, expositions,
risque et changements de politique. Sept jours ne prouvent pas une rentabilité future.

## Persistance, budget et autonomie

Transactions financières courtes, journal append-only, cash réconcilié avec le
ledger, verrou de session PostgreSQL. Une réponse READY persistante est réutilisée
après interruption tant qu'elle reste valable. Quotas et réservations de coût
survivent aux rollbacks.

Plafond autorisé : **100 EUR de crédits Azure au total et 20 EUR/jour UTC**, estimés
prudemment avec les tarifs du propriétaire. La facture Azure fait foi.
L'offre effective étant inconnue, l'estimation prudente est conservée à sa demande.
Maximum 72 sessions/jour, chacune pouvant contenir plusieurs requêtes. Les événements
peuvent déclencher une réflexion après 10/30 minutes, dans les mêmes quotas 12/4.

Cron GitHub 09/19/29/39/49/59, secours Supabase toutes les deux minutes, secours
Cloudflare indépendant toutes les cinq minutes. Les trois utilisent encore GitHub
et Supabase ; aucune disponibilité absolue n'est garantie. Le dashboard expose
heures et sources des cycles, erreurs partielles, tokens et budget estimé.

## Déploiement et sauvegarde

[Guide gratuit](docs/DEPLOYMENT.md). Un dépôt privé avec GitHub Pro reste soumis au
quota partagé du compte ; ne pas autoriser de dépassement payant. Les quotas
d'egress, Realtime et builds dépendent aussi du trafic.

Daily paper competition backup exporte chaque jour à 03:43 UTC, artifact conservé
14 jours. JSON/CSV incluent les tables de compétition, mais pas les secrets Vault
ni la configuration d'administration des fournisseurs. L'export utilise une vue
transactionnelle cohérente et ne bloque pas une analyse IA en cours.

Pour restaurer **dans une base séparée et vide**, appliquer les migrations à cette
base, définir RESTORE_DATABASE_URL puis :

```powershell
.venv/Scripts/python operations/restore_export.py --directory exports/week-01
```

Le programme refuse une base contenant déjà une expérience, réconcilie les soldes
et désactive le scheduler restauré. La CI teste la restauration dans PostgreSQL
jetable. Un pg_dump reste adapté à une sauvegarde complète du serveur PostgreSQL.
Ne jamais écraser l'expérience active. Exports et secrets restent hors Git.

## Arborescence

```text
survival/       agents, modèles, providers, recherche, données primaires,
                analytics, simulateur, tâches récupérables, DB, rapports, CLI
config/         règles centrales et tarifs Azure du propriétaire
supabase/       migrations 001–003 et secours Supabase
frontend/       React/TypeScript/Vite, dashboard réel et démo isolée
scheduler/      Worker Cloudflare de déclenchement indépendant
operations/     déploiement Worker, compte DB limité, restauration
tests/          unitaires, régressions, API opt-in, PostgreSQL jetable
.github/        cycles, CI, sauvegarde quotidienne
docs/           audit, traitement des 40 points, déploiement, validations
```

[Validations effectuées](docs/VALIDATION.md). Les documents v2/v3/v4 décrivent les
phases historiques ; les règles courantes sont ce README, settings.json et
REMEDIATION.md. Un contrôle non exécuté n'est jamais annoncé réussi.
