# Participation des HUNTER et SPRINTER

## Validation réelle du 13 octobre 2026

La politique a été appliquée à 16:12:02 Paris dans le cycle [38411257084](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38411257084). Les quatre IA ont choisi et exécuté leur premier achat fictif dans cette session :

| Agent | Marché choisi | Outcome | Budget EUR frais inclus, arrondi | Type |
|---|---|---|---:|---|
| A1 HUNTER | Bitcoin au-dessus de 86 000 USD le 14 octobre | YES | 1,00 | EXPLORATION |
| A2 SPRINTER | Gemini 4.0 publié au 13 octobre | NO | 1,00 | EXPLORATION |
| A6 HUNTER | Aucun changement de taux Fed à la réunion d'octobre | NO | 5,00 | EXPLORATION |
| A7 SPRINTER | 90–114 publications Elon Musk du 12 au 14 octobre | YES | 5,00 | EXPLORATION |

Les quatre décisions sont UNESTIMATED : aucun avantage probabiliste n'est revendiqué. Les ordres sont FILLED, les minimums respectés, chaque fill correspond aux prix et quantités du carnet enregistré, et les frais recalculés correspondent aux frais persistés. Les soldes correspondent au journal financier. L'écart infinitésimal avec exactement 1/5 EUR vient de la précision de quantité et de frais, pas du change.

Le cycle automatique suivant [38411306587](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38411306587) a conservé exactement ces quatre opérations sans répétition forcée, et actualisé les valorisations. Le dashboard public affichait les quatre obligations remplies à 16:17:35. Les six autres agents sont restés discrétionnaires. Les échéances de participation du 14 octobre à 16:12:02 sont donc déjà satisfaites ; celle de la compétition reste le 19 octobre à 22:36:07.

La politique participation-v3 concerne uniquement A1/A6 HUNTER et A2/A7 SPRINTER. Elle commence à sa première application dans un cycle persistant, sans remettre les comptes à zéro ni changer la fin de la compétition. Les six autres agents gardent leurs décisions discrétionnaires et leurs fréquences.

## Règle

Chaque agent concerné doit effectuer un premier investissement fictif sous 24 heures, au plus tard avant la fin de l'expérience. Une opération stratégique reste prioritaire. Sans thèse convaincante, il doit choisir une petite opération EXPLORATION sur un marché qu'il a lui-même recherché et inspecté. Dès qu'au moins une option exécutable est disponible dans sa session, la réponse attendue est BUY. Une réponse WAIT déclenche au maximum une correction du modèle ; un refus persistant est journalisé comme ParticipationContractError, jamais converti en achat automatique.

L'IA choisit le marché, l'outcome et son plan de sortie. Le système fournit des aperçus d'exécution calculés sur les carnets des marchés inspectés ; ces aperçus ne sont pas des fills. Le carnet choisi est à nouveau rafraîchi avant l'ordre fictif.

Exploration : cible 10 % du capital initial en unité de cotation, frais inclus. Un minimum réel peut porter le budget à 20 % au maximum, avec toujours les contraintes de liquidité, tick, frais, fraîcheur, solde et profil applicables. Si aucune option n'est exécutable ou si une vraie pause de drawdown s'applique au SPRINTER, l'agent peut attendre. Une évolution du carnet peut aussi faire rejeter l'ordre. Les exigences de participation ne permettent aucun prix inventé, emprunt ou minimum contourné. Un dépassement de l'échéance reste explicitement affiché.

Un premier BUY effectivement exécuté, stratégique ou exploratoire, remplit l'obligation. Aucune autre exploration obligatoire n'est autorisée après ce premier investissement. Les achats stratégiques, ventes et décisions WAIT restent ensuite libres dans le profil de l'agent.

## Transparence

Les décisions et ordres portent decision_kind=STRATEGIC ou EXPLORATION. Le fil d'activité affiche ce type. Si la probabilité est inconnue, probability_basis=UNESTIMATED impose le repère technique 0.5, une confiance nulle et expected_edge=0. Ce repère n'est pas une prévision : le dashboard affiche « non estimée » et verified_edge=null. Il n'est pas utilisé pour revendiquer un avantage positif.

Le dashboard affiche les quatre échéances et leur statut PENDING, FULFILLED ou OVERDUE. La règle et sa date sont conservées en mémoire ainsi que dans l'historique des politiques ; les rapports finaux conservent les nombres d'explorations. Les opérations exploratoires comptent dans le capital, les frais, pertes et ROI réels du simulateur. Elles ne prouvent pas un intérêt stratégique ou une rentabilité future.

## Configuration et coût

Les paramètres sont dans config/settings.json, section participation : agent_ids, deadline_hours, target_fraction, max_fraction, retry_calls. Les risques des six agents standards ne changent pas. Les agents dynamiques conservent 12 sessions maximum par jour, les standards 4. Une revue initiale des quatre agents concernés peut être déclenchée à l'application de la politique, sans dépasser les quotas journaliers.

La recherche garde trois tours d'outils et une réponse finale. Avant le premier investissement seulement, une réponse omettant BUY malgré des options disponibles peut ajouter une complétion de correction, soit cinq au maximum dans cette session. Aucune correction de participation après satisfaction de la règle. cost-report distingue ce supplément borné des scénarios de recherche de base. Son plafond très pessimiste est 336 complétions supplémentaires sur sept jours si les quatre agents ne remplissaient jamais leur obligation ; il ne s'agit pas d'une prévision.

Cette règle vise à éviter une compétition entièrement inactive. Elle change l'objectif expérimental : une partie des investissements peut résulter d'une obligation de participation et non d'un avantage estimé.
