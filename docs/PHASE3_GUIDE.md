# PROJECT SURVIVAL — Phase 3

## Ce qui fonctionne

Un fonds commun de **1 000 € fictifs**, cinq spécialistes, quatre membres permanents et un secrétaire sans vote. Les anciens comptes ne sont pas réinitialisés. Le site principal présente le conseil ; `?phase=1` et `?phase=2` conservent les anciennes interfaces.

Le déploiement ne lance pas le défi. **Seul START crée les 168 heures.** Aucun wallet ni chemin d’ordre réel n’existe dans le moteur opérationnel.

## Organisation

| Membre | Fonction |
|---|---|
| Thomas Morel | Météo |
| Sofia Laurent | Football |
| Malik Bennett | Basketball |
| Elena Varga | Tennis |
| Alex Chen | Esport |
| Gabriel Weiss | Quant |
| Nadia Diallo | Risk Manager |
| Victor Shaw | Contradicteur |
| Claire Beaumont | Chairman |
| Camille Rousseau | Secrétaire, sans vote |

Le spécialiste réalise son analyse indépendamment. Une proposition exploitable rejoint l’ordre du jour. Le Quant, le Risk Manager et le Contradicteur interviennent séparément ; le Chairman pose une question utile et peut proposer un amendement ; le membre concerné répond. Ensuite, les cinq membres votent simultanément, sans voir les votes courants des autres.

Le vote porte sur **le marché, le côté, la somme et le prix maximum**. Changer une proposition invalide ses anciens votes. Un changement de marché exige un dossier déjà analysé par le spécialiste compétent et un nouvel examen du conseil.

Il faut au moins quatre votes POUR/CONTRE exprimés et trois POUR pour une approbation ordinaire. Une abstention doit identifier un blocage essentiel et une condition de réexamen. En cas d’égalité, les abstinents sont interrogés une fois ; si l’égalité demeure, le Chairman peut approuver, refuser ou annuler, même en contredisant son premier vote. Une absence provoque d’abord une pause avec tentative de rétablissement. Quatre membres peuvent décider avec quatre votes exprimés ; le Chairman est indispensable. Deux absences annulent.

Le Risk Manager ne dispose pas d’un veto discrétionnaire. Le backend contrôle les impossibilités : fonds insuffisants, proposition invalide, calendrier incohérent, marché fermé, frais inconnus, prix limite, minimum, tick, profondeur ou données d’exécution indisponibles. Il n’impose ni plafond de prudence par mise, ni avantage positif arbitraire, ni quota financier Azure. Une incertitude argumentée reste une décision du conseil.

## Rythme et autonomie

- Collecte Polymarket toutes les dix minutes.
- Réunions à **9 h, 13 h, 17 h et 21 h, heure de Paris**, avec gestion du changement d’heure.
- Analyse réutilisée pendant deux heures, sauf mouvement significatif d’environ quatre points de prix. Les marchés déjà investis sont exclus.
- Jusqu’à trois dossiers par réunion, sélection diversifiée par domaine ; pas de remplissage artificiel.
- Réunions extraordinaires : urgence avant la prochaine session, priorité suffisante, regroupement, délai de 45 minutes et quatre convocations maximum par jour par défaut. Ces paramètres anti-abus sont modifiables dans `council/src/domain.ts`.
- Réunion limitée à dix minutes, sans durée minimale ou attente théâtrale. La répétition vérifiée a duré **38 secondes** : les appels indépendants sont parallèles.

Les alarmes et l’état des réunions sont stockés dans Cloudflare. Le PC et le dashboard peuvent être fermés. Le navigateur ne pilote jamais le moteur. Les baux sont renouvelés pendant les tâches ; une interruption permet une reprise après environ deux minutes, sans répéter un débit.

Une réunion sans dossier produit un bilan déterministe, distinct d’un débat réellement tenu. Le nombre de dossiers et d’investissements demeure un objectif de qualité, pas un quota de paris obligatoires.

## Marchés et données

Le backend recherche et classe les marchés, conformément au cadrage de cette phase. Les agents ne font pas de recherche libre du catalogue. La collecte parcourt jusqu’à 120 événements par tag et par scan, puis sélectionne trois événements distincts par domaine selon liquidité, échéance, nouveauté et disponibilité prévisible des sources. Cette couverture est bornée et ne représente pas tout Polymarket.

Les endpoints publics Gamma, CLOB et Data correspondent au SDK unifié Python conservé dans le projet. La collecte edge utilise leurs API REST documentées. Les versions v1/v2, les identifiants d’outcomes et les noms réels des équipes sont conservés. Les frais proviennent de chaque marché ; leur absence de configuration bloque l’exécution.

Les données externes sont mutualisées : Open-Meteo/NWS, ESPN et OpenDota. ESPN refuse certains accès Cloudflare et OpenDota limite les IP partagées : le collecteur Python GitHub récupère leurs données publiques et transmet un cache horodaté au conseil. **Cloudflare déclenche aussi ce collecteur lorsque les données ont plus de 25 minutes** ; le cron GitHub reste un secours. Aucun proxy de contournement géographique ni API payante n’est utilisé.

Le cache de recherche expire après une heure. Une source absente n’est jamais remplacée par une information inventée. Les grilles météo restent identifiées comme des prévisions près d’une station, pas comme son observation finale. La station mentionnée dans les règles est privilégiée lorsqu’elle est reconnue. La couverture des villes et compétitions est limitée aux adaptateurs disponibles ; certaines informations, notamment blessures, compositions et patchs, peuvent manquer.

Les marchés en cours restent possibles lorsqu’ils sont encore ouverts et dans la fenêtre temporelle. Les agents doivent distinguer les données antérieures d’un état réellement actualisé. Un carnet récent ne prouve pas un score sportif en direct.

## Comptabilité

Le taux EUR/USD ECB via Frankfurter est figé au START. Les calculs opérationnels utilisent **Decimal.js**, avec précision 40 ; la référence Python utilise `Decimal`. Cent cas identiques vérifient les deux moteurs. Aucune opération monétaire du backend n’utilise un flottant binaire.

Les achats immédiats consomment les asks observés, dans la limite votée, avec la profondeur disponible et les frais du marché. Une exécution peut être partielle ou refusée. Les preuves des carnets sont archivées ; une même liquidité déjà consommée dans la simulation n’est pas réutilisée sur un hash inchangé. Les minimums portent sur l’ordre soumis, pas sur chaque fragment exécuté.

`observed_at` désigne la réception effective d’un carnet par une nouvelle requête publique. `exchange_at` conserve l’horodatage transmis par la place : un carnet inchangé peut avoir un ancien horodatage d’échange sans être une ancienne observation du système. Une observation sauvegardée de plus de trois minutes est inutilisable pour simuler un fill.

La base SQLite est l’unique autorité financière. Débit, position et fills sont atomiques ; des identifiants permanents empêchent les doubles achats. Des triggers interdisent UPDATE/DELETE du journal financier.

Les paris restent détenus jusqu’au règlement officiel. Le dashboard montre le disponible, le coût engagé et les gains/pertes réglés ; il ne présente pas le coût des paris ouverts comme une valeur de revente garantie.

## Fin des sept jours

La fin estimée de l’événement doit précéder la fin du défi d’au moins six heures. Le calendrier métier est distingué de `endDate`, qui peut être un délai de règlement. Une journée météo couvre toute la journée locale. Les sports utilisent le début annoncé et une enveloppe prudente de durée ; elle ne garantit pas la durée réelle.

À la fin, aucune nouvelle décision n’est permise. Les positions sont réglées selon les payouts officiels, jamais selon un simple dernier prix. Un règlement fournisseur retardé conserve le fonds en **CLOSING**, avec montant engagé et incident explicites. Aucun zéro artificiel ni résultat inventé ne sert à forcer la clôture.

Quand tous les paris sont réglés, le rapport final conserve résultat net, ROI, frais, catégories, calibration, drawdown réalisé, participation des spécialistes, réunions tenues, ponctualité, cycles attendus/complets/manquants et consommation Azure. Les objectifs 20 dossiers, 10–20 investissements et 95 % sont évalués, sans être présentés comme garantis. Le suivi des issues des refus peut continuer ensuite, sans toucher au résultat financier final.

## Mémoire et décisions non retenues

Le secrétaire conserve documents, interventions, propositions et votes. Il peut retrouver les documents et les événements passés à la demande d’un membre. Un contexte court présente les résultats et dernières leçons, plutôt que toute l’archive. Une demande sans information nouvelle ne provoque pas automatiquement un second appel au modèle.

Les règlements produisent un retour factuel : probabilité initiale du spécialiste, résultat, profit net et score de Brier lorsque l’issue est binaire. Les annulations sont exclues de ce score. Les modèles ne sont pas réentraînés : ils reçoivent ces retours dans leur prochain contexte.

Pour chaque refus/attente, une référence indépendante de 10 € utilise les prix observables. La cohérence initiale, selon la probabilité subjective et les motifs, reste séparée de l’issue. Un prix non observable donne « gain non calculable », pas un faux gain nul. Une issue gagnante ne prouve pas que le refus était une erreur.

## Lecture sur téléphone et ordinateur

Sur téléphone, le sélecteur « Explorer » permet de changer de rubrique sans faire défiler un menu horizontal. Les interventions utilisent un texte de 16 px et les justifications des votes de 15 px. Le débat suit le défilement normal de la page. « Mode lecture » masque la salle et les indicateurs pour se concentrer sur les échanges ; « Afficher la salle » rétablit la vue complète. « Lire les échanges » rejoint le compte rendu et « Dernier échange », accessible pendant la lecture mobile, rejoint la dernière intervention. L’arrivée de messages ne déplace pas automatiquement la lecture.

Sur ordinateur, la navigation latérale et la salle autour de la table sont conservées. Les textes du débat sont aussi agrandis, les lignes limitées pour faciliter la lecture et le mode lecture reste disponible. Les animations respectent la préférence de réduction des mouvements.

Vérification visuelle en navigateur : largeurs de 320, 390, 430, 768 et 1 440 px, sans débordement horizontal du conseil ; les sept rubriques ont également été parcourues à 390 px. Ce contrôle de mise en page ne remplace pas une vérification sur Safari iOS réel.

## Notifications iPhone

L’iPhone est abonné à ntfy. Le topic n’est pas intégré au frontend public.

Les débuts, fins et incidents déclenchent le relais GitHub ; le conseil continue sans l’attendre. Lors du test serveur, la notification a été remise à ntfy **9,6 secondes après sa création**. C’est une mesure, pas un délai maximal garanti : GitHub et iOS peuvent retarder la réception. Un secours programmé tente aussi de vider la file. L’utilisateur a confirmé le 30 octobre 2026 avoir reçu le nouveau test sur l’écran de son iPhone verrouillé.

Le jeton existant, limité aux Actions du dépôt, a été réutilisé. Son expiration vérifiée est le **12 novembre 2026 à 09:47 UTC**, au-delà d’une semaine lancée le 30 octobre. Si le lancement est reporté, vérifier ce délai. Aucun jeton ne doit être copié dans le chat.

## Coûts

Les chiffres de l’interface concernent ce fonds et les précontrôles de son instance. Les répétitions isolées utilisent le même déploiement Azure mais leur compteur est séparé ; la facture Azure inclut les deux.

La répétition NBA a utilisé 12 appels réussis pour un débat et un pari d’environ **76,37 € fictifs** : coût estimé **0,125 à 0,280 €**, suivant les tarifs fournis. Les frais de marché de ce pari étaient **nuls**, conformément à sa configuration ; ce n’est pas une règle générale des autres marchés.

| Scénario sur sept jours | Estimation Azure indicative |
|---|---:|
| Environ 30–80 analyses/jour, quatre conseils/jour | 6–20 € |
| Environ 100–200 analyses/jour, conseils et quelques extraordinaires | 15–45 € |
| Très nombreux mouvements et centaines/milliers d’analyses/jour | Peut dépasser 100 € |

Il n’y a **pas de plafond monétaire automatique**, conformément à la demande. Ces projections ne sont pas des devis : durée des réponses, cache, fréquence des mouvements, documents supplémentaires et retries changent la consommation. Les fourchettes utilisent 1,76/8,80 € à 4,23/15,84 € par million de tokens entrée/sortie, avec déduction du cache lorsque mesuré. Le déploiement est `gpt-6.1-sol-3`.

Les deux tentatives normales d’un appel sont bornées ; une reprise après panne peut ouvrir une seule vague supplémentaire après backoff, avec quatre tentatives au maximum pour le même identifiant logique. Les réponses perdues restent marquées UNKNOWN : leur coût n’est pas prétendu nul. Le circuit breaker traite les pannes et les 429, pas un budget financier.

L’infrastructure utilise les offres gratuites : Cloudflare Workers/Durable Objects SQLite, Pages et Actions Linux standard sur dépôt public. Aucun abonnement payant n’a été activé. Les quotas gratuits restent des limites réelles. Référence : [tarification Durable Objects](https://developers.cloudflare.com/durable-objects/platform/pricing/) et [limites](https://developers.cloudflare.com/durable-objects/platform/limits/). Les requêtes de l’API exposent les lectures/écritures SQLite du snapshot pour permettre des mesures ; les agrégats Azure sont mis en cache.

## Supabase et conservation

La phase 3 n’écrit pas dans Supabase et ne dépend pas de sa disponibilité. Ses historiques restent conservés. Les dashboards des phases 1 et 2 lisent désormais des **archives finales figées hébergées avec Pages**, de 1,34 Mo et 1,03 Mo avant compression : ils ne pollent plus Supabase et n’ouvrent plus de canal Realtime. Les snapshots sont issus des projections publiques réellement terminées, avec identifiant et statut vérifiés.

Les anciens cycles et sauvegardes automatiques GitHub des phases finies ont été retirés du planning ; les commandes manuelles subsistent. Le cron de l’ancien watchdog Cloudflare a été désactivé. Son code utilise désormais un heartbeat de **137 octets mesurés**, au lieu de télécharger toute la projection historique, si on le réactive.

Le nouveau stockage conserve les états courants, un journal compact et des preuves dédupliquées. Les caches expirés peuvent être supprimés ; les écritures financières et débats sont conservés. Aucune purge destructive des phases précédentes n’a été effectuée. La console Supabase peut continuer à afficher le dépassement de l’ancien cycle de facturation ; déplacer les nouvelles écritures ne réécrit pas son historique de quotas.

## Commandes utiles

Depuis `C:\Dev\PROJECT SURVIVAL`, avec le venv existant :

```powershell
# État réel, sans START ni appel IA.
.venv/Scripts/python.exe operations/council_admin.py health

# Précontrôle explicite : petit appel Azure et cinq tâches de vérification.
.venv/Scripts/python.exe operations/council_admin.py preflight
.venv/Scripts/python.exe operations/council_admin.py state --output exports/phase3-readiness.json

# Tests hors réseau et compilation.
npm.cmd ci --prefix council
npm.cmd run check --prefix council
npm.cmd test --prefix council
npm.cmd run build --prefix council
.venv/Scripts/python.exe -m pytest -q
npm.cmd run build --prefix frontend

# Répétition sur un véritable marché, dans une instance de validation neuve.
# Le spécialiste peut décider d’attendre : aucune réunion ne doit alors être forcée.
.venv/Scripts/python.exe operations/council_admin.py rehearse --instance validation-mon-test --market ID_GAMMA_ACTIF
.venv/Scripts/python.exe operations/council_admin.py export --instance validation-mon-test --output exports/validation.json

# Cette commande seule lance le fonds principal pour sept jours.
# À exécuter uniquement lorsqu’on décide effectivement de commencer.
.venv/Scripts/python.exe operations/council_admin.py start --confirm survival-003
```

Un START répété échoue ; il ne remet jamais le capital à zéro. Le bouton de consultation du frontend n’a aucun secret d’administration.

## Sauvegarde, rapport et export

Le workflow `Council daily archive` exporte tous les documents et tables persistantes en JSON compressé, conservé sept jours dans les artifacts GitHub. Il peut aussi être déclenché manuellement.

```powershell
.venv/Scripts/python.exe operations/council_admin.py export --output exports/phase3/council.json
.venv/Scripts/python.exe operations/council_report.py --input exports/phase3/council.json --output exports/phase3/rapport
```

L’export produit `rapport.html`, lisible hors ligne, et sept CSV : journal financier, paris, réunions, votes, interventions, occasions non retenues et consommation Azure. `council_report.py` accepte aussi un `.json.gz` téléchargé depuis GitHub. Les CSV utilisent UTF-8 et le séparateur point-virgule.

Pour vérifier une restauration, utiliser une **nouvelle instance de récupération en lecture seule** :

```powershell
.venv/Scripts/python.exe operations/council_admin.py restore --instance recovery-audit-1 --input exports/phase3/council.json --confirm survival-003
.venv/Scripts/python.exe operations/council_admin.py export --instance recovery-audit-1 --output exports/phase3/restored.json
```

Cette vérification ne remplace pas le fonds actif et ne relance aucune réunion. La reprise habituelle d’un processus interrompu utilise directement le stockage durable et les baux. Un rétablissement opérationnel après perte complète de la base exige une intervention d’administration : il ne doit pas écraser silencieusement un journal actif.

## Développement et déploiement

```text
council/src/domain.ts       Rôles, schémas et paramètres centraux
council/src/finance.ts      Decimal.js, carnets et votes
council/src/repository.ts   SQLite, transactions et journal
council/src/markets.ts      API publiques et sources vérifiables
council/src/azure.ts        JSON strict, cache, reprises, coûts
council/src/engine.ts       Analyses et machine à états du conseil
council/src/worker.ts       API, alarmes et WebSocket hibernable
council/src/report.ts       Évaluation finale déterministe
council/test/              Tests et 100 références Decimal Python
frontend/src/phase3*        Conseil, historique et performances
operations/council_*       Administration, collecte et exports
.github/workflows/         Vérification, relais et sauvegardes
```

Le choix de TypeScript pour le moteur opérationnel permet l’hébergement persistant gratuit sur Cloudflare sans serveur Python payant. Python reste pour les collecteurs, rapports, tests de référence et anciennes phases. Le SDK Python unifié n’est pas remplacé par `py-clob-client` : l’edge en transpose les endpoints publics documentés, sans importer de fonctions d’ordre réel.

Après modification : tests, `python operations/council_admin.py deploy`, commit/push du frontend pour Pages. Les secrets `.env` sont exclusivement backend. Pour configurer un autre dépôt, `operations/council_github_setup.py` utilise PyNaCl et le gestionnaire de credentials Git ; ne jamais ajouter un secret au frontend ou à un commit.

La démonstration `?phase=3&mode=demo` est un replay statique **explicitement identifié**, issu de la répétition NBA isolée. Elle ne se connecte pas au WebSocket de production et n’injecte aucune activité dans la compétition.

## Preuves et limites de validation

- 47 tests Node du conseil réussis à ce stade, dont 100 cas de parité Python Decimal dans un test de corpus.
- 132 tests Python réussis localement ; quatre intégrations opt-in non exécutées localement. Le précédent contrôle GitHub avec PostgreSQL a réussi.
- Azure : déploiement `gpt-6.1-sol-3` vérifié, puis 12 appels de répétition réussis.
- Cinq domaines : marchés et sources externes vérifiés depuis le système déployé (contrôle du 30 octobre 2026 à 00:12 UTC : cinq domaines disponibles, Azure disponible). Les variantes d’un même match sont regroupées et les abréviations d’équipes ne sont rapprochées que dans leur championnat identifié.
- Répétition NBA réelle : cinq votes POUR, achat fictif de 84,999 unités au prix limite de 0,29, frais 0, portefeuille de validation uniquement.
- Deux marchés historiques : résolution officielle NO puis YES vérifiée avec transactions UMA. La branche v2 dispose de tests de contrat ; aucune exécution réelle de validation v2 n’a été revendiquée.
- Restauration isolée : tables financières, votes, propositions, événements et appels identiques à la sauvegarde vérifiée.
- Notification serveur : relais GitHub réussi, remise à ntfy mesurée à 9,6 secondes ; réception sur l’écran de l’iPhone verrouillé confirmée par l’utilisateur le 30 octobre 2026.
- Lecture publique : 25 requêtes de contrôle abouties, médiane 62 ms, maximum 203 ms ; au plus 137 lignes SQLite lues par requête sur cet état de préparation. Cela ne mesure pas une semaine de charge réelle.
- Stockage de préparation : environ 17 Mo dans le Durable Object. Les artefacts GitHub existants représentent environ 381 Mo ; leur rétention reste limitée à sept jours pour les nouvelles sauvegardes. Aucune donnée phase 3 n’est écrite dans Supabase.

Les contrôles et délais mesurés ne garantissent ni disponibilité à 100 %, ni profit, ni nombre minimal d’investissements. L’interprétation sémantique d’un modèle peut être erronée malgré un JSON valide ; le débat et les citations réduisent ce risque sans le supprimer. Le journal garde aussi les incidents de préparation et les corrections, plutôt que de les effacer.
