# Apprentissage individuel des agents

La politique `learning-v4` ajoute une boucle de retour d'expérience sans relancer la compétition, changer les soldes, les limites de risque ou les quotas de réflexion. Les modèles ne sont pas réentraînés : les faits et les adaptations proposées sont conservés dans une mémoire que l'agent relit lors de sa prochaine analyse.

## Faits observés

À chaque cycle, `survival/learning.py` reconstruit la mémoire depuis l'intégralité du journal financier append-only et des décisions associées, propres à cet agent. Les listes abrégées du dashboard ne servent pas de source. Les opérations antérieures à cette version sont donc reprises. Le mécanisme est déterministe et ne double pas les résultats lors d'une relance.

- Achats : thèse, plan de sortie, probabilité/confidence éventuelles, caractère stratégique ou exploratoire.
- Ventes et résolutions : P&L réalisé net des frais, sortie partielle ou totale, contexte des entrées, motif de sortie, catégorie connue du marché.
- Statistiques cumulées : sorties positives/négatives/neutres, P&L réalisé, frais de toutes les exécutions (y compris les achats encore ouverts), résultats par catégorie.
- Calibration : score de Brier sur les estimations YES dont les titres restants ont effectivement atteint une résolution binaire. Les explorations sans estimation en sont exclues. Une vente bénéficiaire avant résolution ne valide pas une probabilité.

Une sortie partielle est un événement, pas une opération complète indépendante. Le moteur utilise le coût moyen : une position issue de plusieurs achats ne permet pas d'attribuer honnêtement tout son gain à une seule thèse. Les pertes latentes, WAIT et ordres rejetés ne sont pas comptés comme échecs réalisés. Les catégories absentes des données restent `Unclassified`.

## Réflexion et adaptations

Le prompt des dix agents demande de consulter `memory.learning`, d'expliquer la pertinence des observations pour la décision actuelle et de renvoyer `learning_review` : au maximum trois objets `{episode_ids, lesson, adaptation}` validés par Pydantic. Les références doivent correspondre à des résultats observés de cet agent. Les références inventées ou appartenant à un autre agent sont exclues de la mémoire et signalées dans les événements, sans transformer une bonne décision de trading en erreur technique.

Les leçons sont marquées `HYPOTHESIS`. L'agent peut revoir une adaptation à sa réflexion suivante ; elle ne modifie pas automatiquement sa configuration de risque. Un gain ou une perte isolé ne prouve aucune causalité. Les paires d'agents ne partagent aucune mémoire.

## Persistance, coûts et observation

La mémoire est sauvegardée dans `agent_memories` et l'état de l'expérience, dans la même transaction que les mouvements financiers. Les événements `LEARNING` et `LEARNING_REVIEW`, ainsi que les réponses complètes dans `agent_decisions`, constituent la piste d'audit exportable par la commande d'export habituelle. Aucune migration n'est nécessaire : les colonnes JSON et les protections RLS existantes s'appliquent.

L'historique complet reste dans le journal. Le contexte transmis au modèle est borné par `config/settings.json` : 8 résultats récents, 10 thèses ouvertes, 3 entrées de contexte par position et 5 revues récentes. Les totaux couvrent l'historique complet. La page de chaque agent affiche les résultats et les adaptations proposées.

Aucun appel LLM supplémentaire n'est ajouté : la revue accompagne la décision au sein des sessions existantes (12/jour dynamiques, 4/jour standards). Elle augmente toutefois les tokens d'entrée et de sortie ; la consommation réelle reste mesurée par `LLM_USAGE` et `cost-report`. Le changement de prompt peut déclencher une revue initiale, dans les quotas habituels. Le système ne garantit pas que l'apprentissage améliorera les rendements.

## Vérifications

`pytest` couvre les gains/pertes nets, les sorties partielles, les entrées multiples, la calibration YES/NO et l'exclusion des probabilités non estimées, le rejet des références étrangères, les limites de mémoire, la reprise de l'audit complet, l'isolation des agents et l'idempotence des cycles. Les fixtures restent limitées aux tests et au mode démonstration.
