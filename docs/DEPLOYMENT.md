# Version courante : survival-v5

Mise à jour **v5.4** : les plafonds de sessions et les blocages sur estimation de
crédits sont désactivés à la demande du propriétaire (`session_quotas_enabled=false`,
`estimated_budget_limits_enabled=false`). Les anciennes valeurs 12/4 et 100/20
mentionnées ci-dessous sont historiques et inactives. Aucune remise à zéro des
portefeuilles ou des compteurs n'est nécessaire. Les estimations sont indicatives,
et l'idempotence des sessions reste active même sans plafond quotidien.

Ce guide garde les étapes de création de comptes. Les règles et limites actuelles
sont détaillées dans [REMEDIATION.md](REMEDIATION.md) et le README.
Budget autorisé : 100 EUR total, 20 EUR/jour UTC de crédits Azure.
Les workflows utilisent DATABASE_URL d'un compte limité. DATABASE_ADMIN_URL reste
local pour migrations et opérations Vault. `operations/provision_runtime.py`
provisionne ce compte et chiffre le secret GitHub avec PyNaCl (dépendance locale
optionnelle : `pip install pynacl`). Ne jamais exposer ces variables au frontend.

Le secours Cloudflare se déploie avec `python operations/deploy_watchdog.py`.
Il nécessite CLOUDFLARE_ACCOUNT_ID et CLOUDFLARE_API_TOKEN limité à Workers Scripts
Write sur le compte concerné. Il reprend le jeton GitHub Actions dédié depuis
Vault sans l'afficher. Le cron s'exécute toutes les cinq minutes, lit la projection
publique Supabase et déclenche un cycle si le moteur est en retard. Il reste soumis
à la disponibilité de GitHub/Supabase. Aucun ordre réel n'est exécuté.

Le workflow backup.yml sauvegarde quotidiennement à 03:43 UTC, artifact 14 jours.
Pour une restauration de données dans une base séparée, vide et migrée : définir
RESTORE_DATABASE_URL puis `python operations/restore_export.py --directory exports/week-01`.
Le scheduler restauré est désactivé ; Vault et secrets fournisseurs se réactivent
séparément. Les vérifications de restauration s'exécutent sur PostgreSQL jetable.

---

# Déploiement gratuit et exploitation

Historique v2 (voir REMEDIATION.md pour les règles v5 actuelles) : lire [AUTONOMY.md](AUTONOMY.md) pour les règles et coûts actuels. Les sessions utilisent Azure Responses v1, les recherches couvrent l'univers public et les tokens sont mesurés. Le timeout GitHub est désormais de 25 minutes. Le tableau de bord n'annonce une planification confirmée qu'après un événement schedule réellement constaté. Avant une augmentation de fréquence, vérifier les crédits Azure et les minutes Actions restantes.

## 1. Supabase Free

Créer un projet gratuit. Dans SQL Editor, exécuter les migrations 001, 002 et 003 dans cet ordre. Sinon renseigner `DATABASE_URL` en local puis `python -m survival.cli migrate`.

Copier la connexion **session pooler** (port 5432) avec mot de passe URL-encodé, et ajouter `sslmode=require`. Éviter le transaction pooler pour conserver un comportement prévisible des connexions de cycle et de quota. Le pooler est utile depuis les runners sans IPv6. Vérifier la migration avant START.

Récupérer l'URL du projet et la clé publique anon / publishable pour le frontend. Aucune clé service_role n'est nécessaire au navigateur. La compétition est volontairement publique via une projection ; les tables internes ne sont pas lisibles avec cette clé.

## 2. GitHub Actions

Créer un dépôt **public** contenant les fichiers du projet pour utiliser les runners Linux standard gratuits. Les dépôts privés ont un quota de minutes : environ 1 008 cycles/semaine peuvent le dépasser. Ne pas activer de runner payant ni de dépassement facturable.

Ajouter dans Settings → Secrets and variables → Actions :

| Secret | Valeur |
|---|---|
| DATABASE_URL | Connexion PostgreSQL session pooler, TLS requis |
| AZURE_OPENAI_ENDPOINT | Endpoint de votre ressource Azure OpenAI |
| AZURE_OPENAI_API_KEY | Clé de cette ressource |
| AZURE_OPENAI_DEPLOYMENT | Nom de déploiement, pas simplement le nom commercial du modèle |

Variables : `EXPERIMENT_ID=survival-001`, éventuellement `AZURE_OPENAI_API_VERSION=2024-10-21`. Choisir un déploiement compatible Responses v1, outils de fonction et Structured Outputs stricts (`json_schema`). Aucun outil d'exécution n'est fourni au modèle. L'endpoint Azure est réglé par l'utilisateur ; un appel réel ne peut être validé sans ces paramètres.

Pousser sur la branche par défaut. Autoriser les workflows GitHub Actions. Le workflow `Checks` exécute les tests unitaires, les tests PostgreSQL sur un service jetable, et le build TypeScript/Vite. Attendre son succès avant START. Les tests API publics sont opt-in pour ne pas dépendre de Polymarket à chaque push.

La planification ne démarre pas une nouvelle expérience : avant START, le CLI signale explicitement qu'aucune compétition n'existe. Un rerun GitHub conserve son identité. Les secrets ne doivent jamais figurer dans Git, les variables VITE, les captures ou des URLs publiques.

## 3. Cloudflare Pages Free

Créer un projet Pages relié au dépôt GitHub :

| Réglage | Valeur |
|---|---|
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Build output directory | `dist` |
| NODE_VERSION | `22` ou version supérieure compatible |

Variables de build publiques : `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_EXPERIMENT_ID`. Optionnel : `VITE_GITHUB_START_URL=https://github.com/OWNER/REPO/actions/workflows/cycle.yml`.

Déployer. Le dashboard apparaît en attente. `?mode=demo` affiche uniquement le fichier de fixtures généré par le moteur. Pour régénérer ces fixtures avant publication : `python -m survival.cli demo`, puis versionner `frontend/public/demo.json`. Ce fichier ne contient aucun secret ni donnée réelle.

## 4. START explicite

1. Vérifier la CI et la commande `python -m survival.cli api-check`.
2. Tester un appel de votre déploiement Azure avec sa configuration habituelle, puis vérifier que le premier cycle produit une décision JSON valide ; les échecs seront visibles dans Live activity.
3. GitHub → Actions → **SURVIVAL cycles** → Run workflow → action **start**.
4. Vérifier que START a réussi, que `started_at` et `end_at` sont affichés, et que dix agents sont présents.
5. Lancer ensuite l'action **cycle** pour le premier passage ; les passages suivants sont automatiques.
6. Vérifier la synchronisation réelle, les éventuels rejets et le quota Azure. Une décision WAIT ou un ordre refusé n'est pas une panne.

Le START récupère EUR/USD, crée les dix soldes et les dix écritures initiales dans une transaction. Il refuse un identifiant déjà existant. La compétition s'arrête logiquement après 168 heures, indépendamment du nombre de cycles.

## 5. Quotas et limites vérifiées

Références consultées le 12 octobre 2026 :

- [GitHub Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions) : runners standard gratuits pour les dépôts publics. [Cron](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) : retards et omissions possibles ; exécution sur la branche par défaut. Le workflow évite le début d'heure.
- [Supabase Free](https://supabase.com/pricing) : 500 MB de base, 5 GB d'egress, 200 connexions Realtime simultanées, 2 millions de messages/mois, taille maximale de message 256 KB. Pas de sauvegardes automatiques gratuites. Pause après une semaine d'inactivité.
- [Cloudflare Pages](https://developers.cloudflare.com/pages/platform/limits/) : 500 builds/mois, un build simultané, fichier individuel limité à 25 MiB. Les cycles ne reconstruisent pas le site.

Un maximum de 504 raisonnements est prévu pour sept jours. Avec quatre marchés et profondeur bornée, le coût dépend du déploiement Azure et des tokens réels ; aucune estimation monétaire inventée. Réduire les fréquences, `markets_per_agent`, `max_llm_tokens` ou la profondeur si nécessaire. Les reprises de SDK et Azure sont bornées ; le job est limité à 25 minutes.

`python -m survival.cli quota-check` affiche la taille PostgreSQL et la projection courante. Le moteur refuse de continuer au-delà de `max_database_bytes`, avant le quota gratuit, pour éviter un dépassement non maîtrisé. La taille inclut le reste du projet Supabase ; privilégier une base dédiée. Consulter également Usage dans Supabase et Azure et Actions Usage dans GitHub. Les quotas d'egress dépendent du nombre de visiteurs ; le budget nul ne peut pas garantir un trafic illimité.

## 6. Pannes, clôture et export

- Données publiques indisponibles : alertes, décisions suspendues, aucun prix de substitution. Les dernières valeurs affichées portent une date ; après vingt minutes le dashboard avertit de leur ancienneté.
- Frais inconnus ou protocole inconnu : marché ignoré avec erreur explicite.
- Azure indisponible ou JSON invalide : aucune transaction de cet agent ; mémoire et réservation de quota conservées.
- Base indisponible ou panne au milieu du cycle : les transactions déjà validées restent conservées ; la tâche READY et le cycle en cours sont repris sans double fill. Relancer le workflow.
- Job bloqué : attendre le timeout et relancer ; le verrou est libéré avec la connexion.
- Clôture : le premier cycle après `end_at` bloque l'IA, règle les payouts attestés, valorise les autres positions et sauvegarde `final_reports`. Le délai du scheduler est affiché. Les positions non liquidables rendent le classement incomplet et leur borne basse est indiquée.

Pour sauvegarder sans PC allumé, déclencher action **export**. Télécharger l'artifact GitHub dans les sept jours. Pour un export local, utiliser le CLI. Les CSV du CLI sont des archives d'exploitation ; les tableaux du dashboard montrent un extrait récent. Faire aussi un `pg_dump` pour une restauration complète. Après la clôture, désactiver le workflow planifié pour ne plus consommer de ressources ; ne pas effacer les journaux.

## Interventions du propriétaire

Créer les comptes gratuits, fournir les secrets dans les interfaces prévues, connecter GitHub à Pages, appliquer la migration, vérifier les services puis déclencher START. Aucun compte ni déploiement distant n'est créé automatiquement par le dépôt. Ne pas transmettre les secrets dans une conversation ou dans le code.
