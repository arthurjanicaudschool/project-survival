# PROJECT SURVIVAL

**10 AI Agents. 7 Days. One Winner.**

Compétition de paper trading : 10 portefeuilles fictifs indépendants, 300 EUR de capital initial total, données publiques Polymarket, analyses Azure OpenAI, comptabilité Decimal et dashboard React. Aucun wallet, clé privée, signature ou appel d'exécution d'ordre réel dans le code opérationnel.

## Démarrage local

Python 3.11+ (vérifié ici avec 3.12), Node 22.12+ (vérifié ici avec 24), PowerShell :

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e '.[test]'
Copy-Item .env.example .env
.venv/Scripts/python -m survival.cli demo
Set-Location frontend
npm ci
npm run dev
```

Ouvrir http://127.0.0.1:5173/?mode=demo. Les chiffres de démonstration proviennent d'un vrai cycle déterministe du simulateur, stocké dans `data/demo.sqlite`. Aucun LLM n'est appelé. Un bandeau identifie les données synthétiques ; elles ne sont jamais utilisées comme solution de repli dans la vue réelle.

Commandes depuis la racine, après activation du venv (ou avec `.venv/Scripts/python` sous Windows) :

```bash
python -m pytest -q
python -m survival.cli api-check
python -m survival.cli demo --cycle-id fixture-001
python -m survival.cli migrate
python -m survival.cli start
python -m survival.cli cycle --cycle-id manual-001
python -m survival.cli quota-check
python -m survival.cli export --output exports/week-01
```

`migrate`, `start`, `cycle`, `quota-check`, `export` utilisent `DATABASE_URL`. `start` récupère un taux de référence EUR/USD et commence **explicitement** l'expérience. Ni l'installation ni le déploiement ne la démarrent. Un second START avec le même identifiant est refusé. Pour une autre compétition, choisir un nouvel `EXPERIMENT_ID`, également côté frontend.

## Déploiement autonome à budget nul

Voir [le guide de déploiement](docs/DEPLOYMENT.md) pour Supabase Free, un dépôt GitHub public et Cloudflare Pages Free. Les comptes et les secrets sont à fournir par leur propriétaire. L'exécution s'effectue chez GitHub et les données chez Supabase : le PC peut être éteint. Les cycles sont programmés aux minutes 07/17/27/37/47/57.

Le dashboard expose la procédure START et peut ouvrir le workflow GitHub via `VITE_GITHUB_START_URL`. Il ne reçoit aucun secret d'administration. L'action START se fait dans GitHub Actions ou dans le CLI, jamais depuis un endpoint public non authentifié.

GitHub Actions n'offre pas de garantie de ponctualité des cron : un cycle peut être retardé ou omis. La date limite reste fixe ; chaque exécution bloque les nouvelles analyses après cette date. Le premier cycle après l'échéance produit le rapport avec le délai de clôture et l'heure effective des carnets. Une valorisation exactement à la seconde 168 h ne peut pas être garantie avec cette infrastructure gratuite. Le rapport ne dissimule pas cette limite.

## Architecture et fichiers

```text
PROJECT SURVIVAL/
├── survival/
│   ├── agents.py       # Dix identités, cinq prompts stratégiques, signaux et fréquences
│   ├── models.py       # Modèles Pydantic, Decimal, carnets et portefeuilles
│   ├── providers.py    # SDK unifié public, frais, historiques, résolutions, FX, Azure
│   ├── engine.py       # IOC, profondeur, frais, risques, ventes, règlements et P&L
│   ├── store.py        # PostgreSQL atomique et SQLite isolé pour les fixtures
│   ├── runner.py       # START, cycle, journal, mémoires, valorisation, classement final
│   ├── fixtures.py    # Données explicitement synthétiques
│   └── cli.py          # Commandes d'exploitation
├── config/settings.json
├── supabase/migrations/001_initial.sql
├── frontend/
│   ├── src/{main.tsx,data.ts,types.ts,style.css}
│   ├── public/{demo.json,_redirects}
│   ├── package.json
│   └── package-lock.json
├── tests/{test_engine.py,test_runner.py,test_providers.py,test_integrations.py}
├── .github/workflows/{cycle.yml,test.yml}
├── docs/{DEPLOYMENT.md,DESIGN.md,VALIDATION.md}
├── .env.example
└── pyproject.toml
```

Le plan technique et les choix de conception sont dans [DESIGN.md](docs/DESIGN.md). La stack demandée est conservée. Seule addition : SQLite pour développer et tester sans compte ; la production utilise exclusivement PostgreSQL Supabase. Les appels SQL transactionnels passent directement par psycopg pour garantir un verrou PostgreSQL et une seule transaction, plutôt que plusieurs requêtes REST indépendantes.

## Agents et configuration

| Stratégie | 10 EUR | 50 EUR | Profil | Appels IA maximum / jour UTC |
|---|---|---|---|---|
| HUNTER | A1 | A6 | Dynamique / momentum | 12 |
| SPRINTER | A2 | A7 | Dynamique / événements courts | 12 |
| ANALYST | A3 | A8 | Prudent / fondamental | 4 |
| VALUE | A4 | A9 | Standard / écart de probabilités | 4 |
| CONTRARIAN | A5 | A10 | Standard / sur-réactions documentées | 4 |

Modifier `config/settings.json` pour les fréquences, concentration, réserve liquide, seuil d'edge, confiance, slippage et cooldown. Le plafond global est 72 raisonnements/jour, soit 504 sur sept jours, avant les filtres de signal. Les tentatives Azure échouées comptent aussi. Un journal de réservation séparément validé empêche de dépasser le quota en cas de crash puis de reprise. Chaque agent a son portefeuille, mémoire et décision distincts.

`estimated_probability` signifie toujours P(YES). Pour NO, Python utilise son complément. `proposed_stake` est un budget total frais compris pour BUY et un objectif de produit brut pour SELL. L'edge effectif est recalculé sur les fills exécutables après frais ; la valeur annoncée par le modèle est conservée seulement pour audit. Aucun achat n'est forcé. Le minimum peut légitimement empêcher un compte de 10 EUR de diversifier ses positions.

## Données et simulation

Le SDK officiel `polymarket-client==0.13.0` est figé. Le collecteur utilise `PublicClient`, Gamma, les carnets CLOB, l'historique Data API v2 et les règlements officiels. Il choisit token IDs pour v1 et position IDs pour v2, refuse les versions inconnues et les frais non documentés. Aucun prix synthétique en cas de panne.

Le marché présélectionné est actif, accepte des ordres, dépasse la liquidité configurée et a une échéance dans les huit jours. Les positions déjà détenues sont toujours recherchées, même sur un marché fermé. Les règles et sources de résolution viennent des métadonnées publiques. Les résolutions ne sont jamais déduites d'un prix proche de 0/1 : elles exigent les payouts et une résolution effective du fournisseur.

Le moteur simule des ordres immédiats IOC contre les niveaux observés. Spread, slippage de profondeur, frais, tailles minimales, tick et soldes sont vérifiés. Les quantités sont arrondies vers le bas à six décimales et les frais à cinq décimales. Les carnets sont rafraîchis après chaque raisonnement réel avant une éventuelle exécution. Les marchés imposant un délai d'appariement sont exclus des nouveaux ordres : leur simulation demanderait une observation différée supplémentaire.

Par défaut, seuls les 12 meilleurs niveaux de chaque côté sont conservés pour limiter le stockage. Il s'agit d'une profondeur observée bornée ; une quantité dépassant cette profondeur est partiellement exécutée ou marquée non liquidable. La valeur nette est la somme du cash et du produit net liquidable au bid. La fraction non liquidable est signalée et vaut zéro dans une **borne basse**, sans prétendre qu'elle n'a aucune valeur économique. La valorisation sous les minimums d'ordre est indicative ; elle ne crée aucun fill de vente.

L'exécution papier observe un carnet mais ne mesure pas une latence réelle, une file d'attente ou l'impact qu'aurait eu un ordre réel. Les dix portefeuilles sont des simulations indépendantes du même marché. Les catégories manquantes sont indiquées comme non classées.

Aucun moteur de recherche commercial n'est nécessaire. La version livrée transmet les règles, historique et sources officielles des marchés. Elle n'intègre pas de flux d'actualités externe ; les agents sont explicitement avertis de cette absence. Les URLs citées doivent appartenir aux preuves fournies ; aucune source inventée n'est acceptée.

## Monnaie et évaluation finale

La comptabilité est en unités de cotation fictives compatibles avec les marchés, avec convention explicite 1 pUSD = 1 USD de référence. Cette convention n'est pas une promesse de peg ou une conversion réelle. Le taux EUR/USD BCE via Frankfurter est horodaté, vérifié et figé au START. Les valeurs EUR sont divisées par ce même taux pendant toute la semaine : aucun gain de change n'est attribué au trading.

À la clôture, les règlements observés sont comptabilisés et les autres positions valorisées au carnet disponible. Le rapport stocke le classement ROI, le gagnant au bénéfice absolu, la survie (`ROI > survival_roi`), les valeurs non liquidables, le rendement / drawdown maximum et la comparaison chiffrée des cinq paires. Les égalités au ROI sont départagées par identifiant. Un classement comportant des positions non liquidables est explicitement incomplet. Cette compétition ne démontre pas une rentabilité future.

## Sauvegardes, export et reprise

`export` écrit `state.json` et les tables d'audit en CSV, y compris ordres, fills, décisions, positions, mémoires, snapshots et rapport final. Le bouton du dashboard exporte uniquement la projection affichée, volontairement limitée aux données récentes. L'export CLI conserve l'historique complet.

Pour une sauvegarde restaurable complète, utiliser le `pg_dump` fourni avec PostgreSQL contre la connexion Supabase appropriée, sans publier le mot de passe :

```bash
pg_dump --dbname="$DATABASE_URL" --format=custom --file=survival.dump
# Restaurer dans une NOUVELLE base dédiée, jamais écraser la compétition active :
pg_restore --dbname="$RESTORE_DATABASE_URL" --no-owner --no-acl survival.dump
```

Sous PowerShell : utiliser `--dbname=$env:DATABASE_URL`. Stocker les exports hors du dépôt public. La reprise d'un cycle utilise l'état transactionnel persistant. Dans GitHub, un rerun conserve le même `run_id`, donc aucune transaction ne peut être appliquée deux fois. Une panne avant commit annule toutes les écritures financières ; les réservations de quota IA restent consommées par prudence.

Les tables financières d'audit refusent UPDATE et DELETE. Ne pas corriger manuellement des soldes : conserver les traces et créer une nouvelle expérience si le protocole d'expérimentation change.

## Vérification

Voir [VALIDATION.md](docs/VALIDATION.md) pour les résultats effectivement obtenus et les contrôles restant à exécuter avec les services configurés. Les tests réseau et PostgreSQL sont opt-in :

```powershell
$env:RUN_NETWORK_TESTS='1'
.venv/Scripts/python -m pytest tests/test_integrations.py -k live_public -q
# Base PostgreSQL dédiée aux tests, jamais la base de compétition :
$env:TEST_DATABASE_URL='postgresql://...'
.venv/Scripts/python -m pytest tests/test_integrations.py -k postgresql -q
```
