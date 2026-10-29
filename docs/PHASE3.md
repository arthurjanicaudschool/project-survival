# Phase 3 - conseil de paris fictifs

## Contrat approuvé

- START explicite seulement ; 168 heures, 1 000 EUR communs, taux EUR/USD figé.
- Météo, football, basketball, tennis, esport ; cinq spécialistes indépendants.
- Quant, Risk Manager, Contradicteur et Chairman rejoignent le spécialiste concerné.
- Secrétaire : journal déterministe et recherche documentaire dans l'archive ; aucune mémoire intégrale envoyée aux agents.
- Proposition versionnée = marché, côté, montant. Toute modification invalide les anciens votes.
- POUR / CONTRE / ABSTENTION motivée. Au moins quatre votes exprimés. À cinq, trois POUR approuvent ; égalité : réinterroger l'abstinent puis arbitrage motivé du Chairman, qui peut annuler et changer d'avis.
- Priorité au report si un membre manque ; à quatre participants, quatre votes exprimés requis et Chairman indispensable. Deux absents annulent.
- Veto exclusivement technique déterministe, aucun plafond de prudence de mise ni de budget Azure. Montant, concentration, incertitude : discussion et vote.
- Aucune revente ; résultats officiels uniquement. Événements terminant au moins six heures avant la fin du défi ; retard officiel reste affiché honnêtement.
- Réunions ordinaires 09/13/17/21 Europe/Paris ; extraordinaires urgentes 24h/24 avec regroupement et anti-abus configurables.
- Notifications début/fin/incident ; aucun spectateur ni appareil utilisateur nécessaire à l'exécution.
- Refus : résultat théorique d'une mise de référence 10 EUR au carnet archivé, séparé du fonds ; non-exécutable explicitement identifié.
- 20 dossiers sérieux, idéalement 10-20 investissements, 95 % réunions et cycles : mesures d'évaluation, jamais quotas de paris.

## Architecture et conservation

Moteur opérationnel TypeScript sur Cloudflare Durable Object SQLite : source financière unique, étapes persistantes, alarmes, WebSocket hibernable. GitHub reste pour tests et sauvegardes. Python reste la référence Decimal et les anciens moteurs. Les phases 1/2 restent accessibles. Aucune migration destructive ni START pendant la construction.

Journal append-only, documents dédupliqués par empreinte, états courants courts, pagination des débats. Aucune répétition du portefeuille complet dans les événements. Caches à expiration séparés des preuves. Contrôles de quota mesurés avec essai avant lancement.

## Validation attendue

Parité Decimal, minimum/tick/liquidité/frais, résolution et FX ; vote/amendements/abstention/absences ; panne Azure, reprises et idempotence ; source indisponible ; retour WebSocket et replay ; sauvegarde/restauration ; charge et consommation Cloudflare. Mode démonstration isolé des données réelles. Répétition technique sur données réelles isolée de survival-003, qui reste READY.

État de construction : en cours. Les preuves de tests et de déploiement seront ajoutées après leur exécution effective.
