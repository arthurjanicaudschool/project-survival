# Fiabilité et secours indépendant de GitHub Cron

Le 13 octobre à 10:33 Paris, un seul cycle GitHub `schedule` était observé depuis la nuit : fin à 05:13. Le dernier résultat réussi ne prouve pas une cadence de dix minutes. GitHub indique que ses événements planifiés peuvent être retardés ou supprimés sous charge : https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule . La cause précise de ces longues absences n'est pas établie.

## Changement

Supabase Cron vérifie toutes les deux minutes si un cycle a besoin de démarrer. Il demande le workflow existant via une requ?te HTTPS directe, sans exécuter le trading dans SQL. Il évite une demande si un cycle est actif, si son début est trop récent, si une demande a déjà été envoyée récemment ou si l'expérience est FINISHED. Le verrou PostgreSQL existant reste l'autorité financière ; les quotas Azure indépendants et l'identité de chaque run empêchent les doubles écritures lors d'une reprise. Une erreur du processus déclenche une seule nouvelle tentative avec le même identifiant GitHub.

Le cron GitHub reste en place comme seconde source de déclenchement. Les deux sources partagent le même workflow, le même verrou et les mêmes quotas. Une panne de GitHub Actions ou de Supabase reste possible : aucun mécanisme gratuit ne garantit 100 % de disponibilité. Ce secours corrige la dépendance exclusive au déclencheur GitHub ; il ne remplace pas les runners GitHub. La cadence reste approximative, notamment pendant une analyse longue ou une file d'attente.

Le dashboard affiche un avertissement après vingt minutes sans cycle terminé, même si un ancien cycle automatique était réussi. Il distingue les déclencheurs et dates GitHub/Supabase. `python -m survival.cli health` calcule l'état courant à la lecture, plutôt que de conserver éternellement un état vert.

Le statut de la dernière analyse est conservé séparément du statut du cycle courant : une actualisation NOT_DUE ne masque pas une précédente panne Azure. L'export CSV inclut la configuration et les journaux scheduler, jamais les secrets Vault ou les en-têtes de requêtes réseau.

## Installation et activation

1. `python -m survival.cli watchdog-install` : installe la migration, pg_cron, http et un contrôle SQL toutes les deux minutes. Les demandes GitHub restent désactivées tant que la clé n'est pas configurée. Réinstaller ne réinitialise aucun portefeuille.
2. Créer une clé GitHub **fine-grained** sur https://github.com/settings/personal-access-tokens/new : propriétaire `arthurjanicaudschool`, **uniquement** le dépôt `project-survival`, permission du dépôt **Actions: Read and write**, Metadata: Read (automatique), expiration couvrant la fin du 19 octobre. Une expiration dans sept jours convient si la clé est créée le 13 octobre. Aucun droit Contents, Administration ou sur d'autres dépôts n'est nécessaire.
3. Ajouter temporairement `SURVIVAL_SCHEDULER_GITHUB_TOKEN=...` dans le `.env` backend local, jamais dans le frontend, Git, une capture ou le chat. Autre possibilité : lancer la commande suivante directement dans un terminal et saisir la clé dans l'invite masquée.
4. `python -m survival.cli watchdog-activate` : vérifie l'accès au workflow, chiffre la clé dans Supabase Vault et active le secours. Le code refuse une clé classique ou la réutilisation automatique des identifiants Git locaux. Le programme n'imprime jamais la clé. Après activation, retirer sa ligne du `.env` si elle n'est plus nécessaire localement.
5. `python -m survival.cli watchdog-status` : vérifier `enabled=true`, le job actif et les demandes récentes. `REQUESTED` signifie seulement qu'une requête HTTP est en attente. `HTTP_RESULT` avec 204 signifie que GitHub accepte la demande ; seul le cycle achevé avec `trigger_source=supabase-watchdog` prouve la chaîne complète.

Les permissions fines effectives et la validité de la clé sont définitivement vérifiées par l'acceptation du POST GitHub. 401/403 signalent une clé expirée, invalide ou insuffisante ; 404 peut masquer un manque d'accès au dépôt. Aucune clé Azure ou service-role Supabase n'est transmise à GitHub par ce contrôleur : le workflow utilise ses secrets déjà configurés.

## Preuves et diagnostic

```sql
select jobname,schedule,active from cron.job where jobname='survival-watchdog';
select status,start_time,end_time,return_message from cron.job_run_details
where jobid=(select jobid from cron.job where jobname='survival-watchdog')
order by start_time desc limit 10;
select created_at,status,request_id,http_status from scheduler_dispatches
where experiment_id='survival-001' order by created_at desc limit 10;
```

Ne jamais consulter ou exporter `vault.decrypted_secrets` pour un diagnostic partag?. Les tables scheduler sont priv?es par RLS, leurs journaux append-only et les fonctions de contr?le ne sont pas ex?cutables par anon/authenticated. Le transport HTTPS synchrone de l'extension http ?vite de conserver la cl? dans une file pg_net : certaines permissions syst?me de cette file ne sont pas r?vocables par le r?le postgres Supabase. Seul le code HTTP est enregistr?, aucun en-t?te, corps de r?ponse ou texte d'exception susceptible de contenir la cl?. Une r?ponse HTTP nulle indique une erreur de transport/extension, pas une acceptation GitHub. Le d?lai r?seau est limit? ? quinze secondes. Les journaux cron de l'installation active mais non configur?e sont de vrais contr?les SQL, pas des cycles de trading.

En cas de panne, les contrôles suivants restent indépendants : statut du job cron, réponse HTTP, statut GitHub et heartbeat Supabase. Pour désactiver les demandes : `update scheduler_config set enabled=false where experiment_id='survival-001';`. Pour désactiver le job : `select cron.alter_job(jobid,active:=false) from cron.job where jobname='survival-watchdog';`. La compétition conserve sa date de fin et son état.

## Budget

Le secours utilise des extensions du PostgreSQL Supabase déjà déployé : aucun nouveau service payant. Au maximum 720 contrôles courts par jour ; les demandes de cycles restent espacées d'environ dix minutes. Les minutes de runners GitHub et les crédits Azure restent limités par leurs offres. Réparer le cron peut augmenter la consommation réelle par rapport à une compétition qui restait bloquée. Il faut suivre ces quotas ; les limites d'offre peuvent interrompre les services. Sources : https://supabase.com/docs/guides/cron ; https://supabase.com/docs/guides/database/extensions/http ; https://supabase.com/docs/guides/database/vault ; https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event .
