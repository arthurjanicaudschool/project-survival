# Validation survival-v5.3 — 14 octobre 2026 (Paris)

## Version courante v5.7 — 18 octobre 2026

Reprise après épuisement des minutes GitHub privées, dépôt rendu public avec
accord du propriétaire. Liquidation réelle en paper trading vérifiée : zéro
position restante, dix NAV complètes, 285,55 EUR fictifs en cash. Conversion de
collatéral et abandon des fractions explicitement journalisés ; gain futur maximal
abandonné inférieur à 0,02 unité. CI : 106 tests Python, un réseau ignoré, cinq tests
Node ; build frontend réussi. Rejeu final hors production : FINISHED sans prix
de marché, sans IA et sans aucune position en suspens.
[Incident, méthodes et preuves de production](INCIDENT-2026-10-18.md).

## Correctif v5.5 : contexte des sessions longues

98 tests Python locaux réussis, 3 ignorés. Deux régressions protègent les règles
de résolution et les contraintes exécutables lors du compactage, ainsi que la
taille de la mémoire de recherche envoyée au modèle. Seuls les six derniers
résumés de recherche sont envoyés ; l'historique et les apprentissages persistent
intégralement en base. Le contexte de travail accepte désormais 120 000 caractères.
Les plafonds de sessions et de dépenses estimées restent désactivés.

Rejeu des outils archivés des derniers échecs A2/A7 avec leur portefeuille et
mémoire réels, modèle simulé : maxima de 90 551 et 101 936 caractères, sans appel
Azure ni écriture financière. Cela valide le chemin de compactage, pas une nouvelle
décision réelle. Les règles, actifs, minimums, ticks, frais, dates et cinq premiers
niveaux des carnets restent accessibles au modèle. Une thèse PRICE_MOVE peut
s'appuyer sur prix et profondeur observés ; l'absence d'actualité externe n'est
pas une interdiction systématique d'investir.

Audit depuis la suppression des quotas, jusqu'au contrôle du 14 octobre vers
16:30 UTC : 136 WAIT et 24 SELL, aucun BUY proposé. Les 24 rejets concernent des
ventes automatiques A6 sous le minimum réel du marché. Aucun achat proposé n'a été
rejeté sur cette période. Le correctif vise les informations manquantes, sans
forcer de transactions ni garantir l'apparition d'une opportunité rentable.

Validation de production : [CI 38599246263](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38599246263)
réussie (100 tests Python, 1 réseau ignoré ; 5 tests Node ; build frontend).
Le [cycle 38599259022](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38599259022)
du commit `cba8008` a terminé avec succès à 16:46:41 UTC : dix nouvelles analyses,
aucune erreur technique de raisonnement, fournisseur marchés opérationnel,
soldes des dix agents réconciliés au journal financier. A2 a répondu à 16:43:54 UTC,
A7 à 16:46:34 UTC. Leur statut WAIT et la politique v5.5 sont confirmés dans la
projection publique Supabase utilisée par le dashboard. Tous les agents ont
choisi WAIT sur ce passage : aucun nouvel achat ni profit n'est attribué au correctif.
Les indisponibilités ponctuelles de sources externes restent explicites et ne
sont pas assimilées à une panne générale du raisonnement.

## Politique v5.4 sans plafonds de sessions ni blocages financiers

96 tests locaux réussis, 3 ignorés ; [CI 38551219764](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38551219764) :
98 tests Python réussis, 1 réseau ignoré, 5 tests Node réussis. Les tests PostgreSQL
vérifient une réservation au-delà des anciennes limites monétaires, sans blocage,
et des sessions sans plafond qui conservent leur idempotence. Build frontend et
déploiement Cloudflare Pages réussis. Le cycle réel
[38551305070](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38551305070)
a démarré sur les contrôles désactivés : A3, A4, A5, A9 et A10 ont terminé une
cinquième session UTC, dépassant l'ancien maximum de quatre. A8 a également repris.
Les quatre dynamiques sont traités ensuite ; aucun compteur historique n'a été effacé.
Le dashboard public affiche « sans plafond quotidien » et « aucun plafond logiciel ».

## Correctif de résolution UMA v1 et d'affichage — 12:23 (Paris)

**95 tests locaux réussis, 3 ignorés ; 97 tests Python CI réussis, 1 réseau ignoré,
5 tests Node réussis**. Deux cycles de production réussis ; les dix valorisations
sont complètes ; total 302,10 EUR, net +2,10 EUR, ROI +0,70 % vérifiés dans le
dashboard public. [Détails et preuves](INCIDENT-2026-10-14.md).

## Livraison précédente

- Tests locaux : **88 réussis, 3 ignorés** (deux PostgreSQL opt-in et un réseau).
- Dernière CI du code : **90 réussis, 1 ignoré**, PostgreSQL 17 inclus, avec restauration JSON/CSV dans une base différente : [38497875877](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38497875877), commit `e6b5374`.
- Build TypeScript/Vite local et Cloudflare Pages réussis ; [dashboard public](https://project-survival.pages.dev/).
- Cinq tests Node du secours Cloudflare réussis, également ajoutés à la CI.
- Requête réelle Azure Responses : modèle gpt-6.1-sol, schéma strict DecisionPlan accepté et validé ; 882 tokens en entrée, 224 en sortie. Aucun ordre issu de ce test.
- Coinbase/BLS/NOAA : réponses structurées obtenues localement. XTracker : erreur TLS de nom d'hôte locale explicitement signalée. Aucune vérification TLS désactivée.
- Migration 003 appliquée après sauvegarde ; compte de cycle survival_runner vérifié, sans UPDATE du ledger ni CREATE sur public ; secret GitHub remplacé par ce compte limité.
- Export distant exécuté : [38486890643](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38486890643), artifact disponible 14 jours. Export local complet également sauvegardé hors Git.
- Worker project-survival-watchdog déployé, cron */5 confirmé. Véritable événement planifié du 13 octobre à 23:55 UTC observé en direct : outcome=ok, scheduler_checked/FRESH, moteur actualisé 26 secondes auparavant. Aucun déclenchement inutile.

Le premier passage réel a révélé un contrôle de contexte trop strict : l'enveloppe
chiffrée du raisonnement était comptée comme du texte de preuves. L'exécution a été
interrompue, le contrôle corrigé et une régression ajoutée (v5.1). Les réservations
de coût restent conservées ; aucun solde ou historique n'a été effacé. Les résultats
des cycles réels après cette correction sont documentés dans les preuves de livraison.
Un deuxième cas réel A1 a révélé le poids des manifestes GIS NOAA et des titres de
recherche. Les mesures, avis et identifiants sont maintenant conservés sous forme
compacte ; les réponses brutes restent archivées. Le rejeu des sept outils de cet
échec tient dans 52 939 caractères, sous le plafond de 60 000, sans nouvel appel IA.
Un rejeu de session complet avec portefeuille et mémoire A1 réels, sept réponses
d'outils archivées et modèle simulé atteint au plus 56 411 caractères. Aucun appel
réseau ni écriture financière pendant ce rejeu. Les grandes pages de recherche
conservent leur JSON, leurs 135 identifiants et leur curseur dans le test de charge
du corps réellement fourni au modèle ; aucun découpage arbitraire de JSON.
Dernier contrôle : les trois traces réelles A1/A5/A7 passent en rejeu complet avec
respectivement 7/14/9 outils et des maxima de 59 639 / 59 267 / 59 019 caractères.
L'encodage Unicode évite l'inflation des échappements tout en conservant les textes.
Ces replays utilisent un modèle simulé, sans appels Azure ni écritures financières ;
ils ne sont pas présentés comme de nouvelles décisions réelles.
Une recherche A1 encore plus longue a été rejouée après ajout d'un dernier
compactage des suggestions initiales et du cache de prix anciens : 10 outils,
maximum 59 848 caractères. Portefeuille, risques, leçons et preuves des marchés
inspectés conservés. Les deux autres replays passent également (14 et 9 outils).
Nouvelle analyse réelle A7 réussie le 14 octobre à 01:44:23 UTC ; WAIT documenté,
trois candidats inspectés. A5 avait atteint son quota quotidien lors de l'échec.
Nouvelle analyse réelle A1 réussie à 01:51:05 UTC sur le correctif `e072ef2` : trois
marchés inspectés, deux pages lisibles, une source structurée, WAIT justifié.
Écritures PostgreSQL désormais en pipeline dans la transaction financière existante,
validées par la CI PostgreSQL du commit `e6b5374`. Mesure en lecture seule de 80 SELECT :
6,068 s séparément contre 0,127 s en pipeline ; pas de prétention de gain identique
sur le temps d'un cycle complet.
Cycle final réellement terminé avec succès sur ce code :
[38497908881](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38497908881),
14 octobre à 02:00:02 UTC, 98,01 secondes. Réconciliation des dix soldes refaite
indépendamment après le cycle. Les quotas et le cache évitent des analyses dues
inutilement ; cette durée ne représente pas dix nouvelles analyses simultanées.

Les validations du 12 octobre ci-dessous restent des observations historiques,
pas une description des accès ni des règles courantes.

---

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
