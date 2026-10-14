# Livraison survival-v5.3 — 14 octobre 2026

Les changements sont publiés sur `main`. Le tableau des
[40 constats et de leur traitement](REMEDIATION.md) distingue les corrections
effectives des limites qui subsistent. L'expérience conserve son capital, ses
positions, son historique et sa fin : **19 octobre 2026 à 22:36:07, heure de Paris**.

## Ce que les agents peuvent désormais faire

- Chercher dans l'univers public des marchés, au-delà des 24 suggestions initiales,
  avec pagination ; choisir leurs outils et leurs sujets de recherche.
- Lire des actualités et des sources primaires ; consulter Coinbase, BLS, NOAA et
  XTracker. Chaque source conserve son horodatage, ses erreurs et ses limites.
- Comparer les coûts minimums frais inclus, le spread, la profondeur, les variations
  et leurs propres hypothèses ; produire jusqu'à quatre actions ordonnées.
- Choisir leurs prix limites et leurs sorties, vendre pour réinvestir, poursuivre
  une thèse de mouvement de prix sans inventer une probabilité de résolution.
- Relire les résultats et hypothèses de leur mémoire indépendante. Le modèle
  n'est pas réentraîné et l'amélioration de rendement n'est pas présumée.

A1/A6 restent libres de prudence imposée. Les contraintes de cash, minimums,
tick, frais et profondeur réelle demeurent. Après leur premier investissement,
les quatre dynamiques peuvent à nouveau choisir WAIT sans achat forcé.

## Preuves techniques

| Vérification | Observation |
|---|---|
| Tests locaux du dernier code | 88 réussis, 3 ignorés : PostgreSQL opt-in ×2, réseau public opt-in ×1 |
| [CI e6b5374](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38497875877) | 90 tests Python réussis, 1 réseau ignoré ; PostgreSQL 17 réel jetable ; 5 tests Node réussis |
| Persistance et récupération | Transactions courtes, verrou concurrent, idempotence et restauration JSON/CSV testés dans PostgreSQL |
| Latence SQL | Contrôle en lecture seule : 80 SELECT, 6,068 s séparément contre 0,127 s en pipeline ; écritures d'état regroupées dans la transaction existante. Ce n'est pas un benchmark de cycle complet |
| Base opérationnelle | Migration 003 appliquée ; rôle limité ; journal append-only ; dix cash réconciliés avec les écritures |
| Accès public | Projection lisible ; ledger, sessions et compteur LLM refusés avec la clé publique |
| Azure réel | Les dix agents ont terminé des analyses indépendantes avec les nouveaux outils ; réponses strictes validées |
| [Cycle réel 38491454843](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38491454843) | Réussite ; les six agents standards avaient alors tous une analyse valide avec la nouvelle politique |
| Vente fictive A7 | Gain réalisé net d'environ 4,69 EUR ; fonds disponibles réconciliés. Aucun achat stratégique supplémentaire n'est prétendu |
| Cloudflare indépendant | Worker déployé ; véritable cron du 13 octobre à 23:55 UTC observé, résultat FRESH, sans doublon inutile |
| [Sauvegarde distante](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38486890643) | Export réussi ; artifact conservé 14 jours ; sauvegarde quotidienne à 03:43 UTC |
| [Dashboard public](https://project-survival.pages.dev/) | LIVE, progression de cycle, erreurs, budget, recherches par agent, classement et valorisations inconnues vérifiés dans le navigateur |

Le [cycle final sur le dernier code](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38497908881)
a terminé avec succès à **02:00:02 UTC le 14 octobre**, en 98,01 secondes. Les dix
soldes correspondent au journal financier. Ce cycle inclut les écritures en
pipeline ; il n'implique pas dix nouvelles réflexions IA. Estimation prudente à
cette date : **34,65 EUR au total, 19,09 EUR aujourd'hui UTC**, une réservation
incertaine conservée. Plafonds 100/20 EUR inchangés.

Les essais réels ont révélé des erreurs de taille de contexte que les premiers
tests n'avaient pas découvertes. L'enveloppe de continuation chiffrée est conservée
sans être comptée comme texte de preuve. Les données redondantes sont compactées,
sans perdre les identifiants, curseurs, mesures ou sources ; les réponses brutes
restent dans l'audit. Le dernier cas A1 (sept outils réels) a été rejoué hors ligne
sous le plafond de contexte. Une analyse échouée reste visible jusqu'à une nouvelle
analyse réussie ; un simple cycle sans raisonnement ne la masque pas.
Le rejeu complet avec portefeuille et mémoire A1 actuels atteint au plus 56 411
caractères. Sa réponse finale est synthétique et n'est jamais enregistrée comme
décision de l'expérience. Le test du corps des outils conserve 135 marchés et leur
curseur dans un JSON valide, même lorsque la réponse initiale dépasse le budget.
Les anciens cycles ont aussi rencontré le plafond chez A5 et A7. Le dernier
correctif conserve le texte Unicode sans inflation d'échappements : les trois
replays A1/A5/A7 passent avec 7/14/9 outils. Leurs anciennes erreurs restent dans
le journal. Une analyse réelle réussie est nécessaire pour effacer l'alerte de
dernière analyse ; A5 avait déjà consommé ses quatre sessions UTC lors de l'échec.
Les quotas ne sont pas effacés pour obtenir artificiellement un état vert.
Un nouveau cas A1 (10 outils) passe après compactage ultime des suggestions
initiales et anciens prix de signal, sans suppression des contraintes ou des
preuves des marchés inspectés. A7 a ensuite terminé une nouvelle analyse réelle
le 14 octobre à 01:44:23 UTC : WAIT justifié après trois candidats inspectés.
A1 a également terminé sa reprise réelle à 01:51:05 UTC : trois marchés inspectés,
deux pages lisibles, une source structurée, WAIT justifié. Seule l'ancienne erreur
d'analyse A5 attend encore sa reprise après renouvellement de son quota quotidien.

## Crédits et fréquence

À la demande du propriétaire, l'offre Azure inconnue conserve une estimation
prudente : **100 EUR pour l'expérience, 20 EUR par jour UTC**, avec réservation
avant chaque requête. Les tarifs retenus pour cette réservation sont les plus
élevés fournis : 5,28 EUR/M en entrée et 15,84 EUR/M en sortie. Les réservations
incertaines et une estimation historique sont incluses ; ce n'est pas une facture.

| Paramètre | Avant v5 | Livraison v5 |
|---|---:|---:|
| Sessions maximum par jour, tous agents | 72 | 72 |
| Sessions maximum sur sept jours | 504 | 504 |
| Tours de recherche / outils par tour | 3 / 3 | 4 / 4 |
| Sortie normale maximale par requête | 1 600 tokens | 2 600 tokens |
| Contrôle global des crédits | Aucun plafond global | 100 EUR / 20 EUR par jour UTC |
| Réessais automatiques cachés du SDK | Possibles auparavant | Désactivés ; réparation explicitement bornée |

Un cycle toutes les dix minutes n'appelle pas nécessairement les dix IA. Les
événements utilisent les mêmes plafonds de 12 sessions/dynamique et 4/standard par
jour UTC. Un cycle contenant plusieurs analyses peut durer plus de dix minutes ;
le suivant attend son tour. La surveillance des sorties se fait à la cadence des
cycles, sans garantie de prix instantané.
Les événements peuvent consommer ces quotas tôt dans la journée. QUOTA_LIMIT est
maintenant distinct de NOT_DUE et le dashboard montre les sessions utilisées ;
atteindre ce plafond n'arrête pas les valorisations, règlements ou sorties définies.

`python -m survival.cli cost-report` donne les quatre scénarios tarifaires sur les
tokens enregistrés. Ses extrapolations mélangent les sessions historiques et
courantes : ce sont des scénarios, pas une prévision fiable du coût v5. La facture
Azure reste la référence. Les quotas GitHub Pro sont partagés avec le compte ; le
solde de minutes n'a pas pu être obtenu par l'API de facturation (HTTP 404).

## Limites toujours visibles

La position Gemini de A2 ne dispose pas d'un carnet exploitable : sa NAV et son ROI
restent inconnus et A2 reste hors classement. Le consolidé demeure indéterminé.
Aucun prix ni résultat n'est fabriqué pour faire disparaître cette alerte.

Les petites poussières observées sous les minimums ou la précision de soumission
apportent zéro cash immédiatement liquidable. Leur valeur économique future n'est
pas supposée nulle ; elles restent signalées et peuvent encore recevoir un payout.

Les recherches gratuites, citations exactes, scénarios quantitatifs et mémoires
ne garantissent ni justesse des thèses, ni diversité réelle entre dix instances du
même modèle. Sept jours et deux agents par stratégie ne suffisent pas à prouver
une supériorité statistique. Le secours dépend encore de GitHub et Supabase ; une
disponibilité de 100 % et des profits ne peuvent pas être garantis.

## Exploitation

Aucun nouveau START n'est nécessaire. Consulter le dashboard, les liens de logs,
`health`, `cost-report` et `quota-check`. Les sauvegardes finales locales sont
conservées dans `exports/v5-final-20261014` hors Git. Une restauration s'effectue
dans une autre base vide, selon le [guide de déploiement](DEPLOYMENT.md).
