# Vérifications effectuées

Exécution locale le 12 octobre 2026, Python 3.12.10 et Node 24.19.0.

| Contrôle | Résultat observé |
|---|---|
| `python -m pytest -q` | **25 passed, 2 skipped** |
| Intégration réseau opt-in `-k live_public` | **1 passed, 1 deselected**, 21,90 s |
| `python -m survival.cli api-check` | **12 marchés, 24 carnets, liste d'erreurs vide** |
| `reference_fx()` | EUR/USD **1.1206**, référence **2026-10-09**, récupérée le 12 octobre ; date acceptée dans la limite de cinq jours |
| Cycle `demo` | Dix portefeuilles valorisés, décisions, ordres, fills, ledger et mémoires écrits dans SQLite isolé ; projection JSON consommée par React |
| TypeScript + Vite | Build production réussi, assets séparés application / Supabase / graphiques |
| `npm install` | 132 packages audités, **0 vulnérabilité rapportée** à cette installation |
| HTTP local | Réponse **200** pour l'aperçu Vite |
| Contrôle navigateur | Overview sombre, classement, filtre 10 EUR = cinq lignes, Performance, fiche agent avec mémoire et explorateur de cotations vérifiés |
| Responsive | Vue desktop 1440×1000 et mobile 390×844 inspectées visuellement |

Les tests locaux couvrent la courbe de frais par marché, absence d'achat au mid, cash non négatif, interdiction des shorts, P&L, règlement gagnant NO, absence de double règlement, carnets périmés, tick invalide, minimums, fills partiels, absence de liquidité, edge NO complémentaire, rejet d'un edge annoncé trompeur, validation JSON, conversion figée, arrondis, dix identités indépendantes, idempotence, rollback après interruption, reprise, verrou concurrent SQLite, fin sans LLM, pannes, quotas, sélection d'identifiants v1/v2 et validation des sources Azure avec un client simulé.

Deux tests sont ignorés par défaut : le contrôle réseau public opt-in, exécuté ensuite séparément avec succès, et le contrôle PostgreSQL nécessitant `TEST_DATABASE_URL`. Docker est installé sur cette machine mais son moteur est arrêté ; aucun PostgreSQL local n'était disponible. **La migration, les verrous PostgreSQL, les RLS et les réservations de quota à deux connexions ne sont donc pas annoncés comme validés ici.** Le workflow `Checks` fournit un PostgreSQL 17 jetable pour les vérifier après publication du dépôt.

Azure : import et interface du SDK vérifiés ; requête JSON et sources testées avec un client simulé. **Aucun appel au déploiement Azure du propriétaire**, aucune connexion Supabase distante, aucun déploiement Cloudflare, aucun START de compétition réelle n'ont été effectués faute de comptes / secrets configurés.

Le cycle démonstration ne démontre pas des performances d'IA. Les prix affichés dans la capture sont des fixtures synthétiques. La fiabilité de sept jours et le respect des quotas de trafic nécessitent une observation sur les services déployés ; un test local ne constitue pas cette preuve.

![Dashboard en mode démonstration](dashboard-preview.jpg)
