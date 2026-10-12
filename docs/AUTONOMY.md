# Autonomie v2 : règles, recherche, preuves et consommation

Cette version s'applique au prochain cycle avec un événement POLICY_CHANGE. Elle conserve les capitaux, portefeuilles, transactions, quotas déjà utilisés et l'échéance originale. Le rapport doit être lu comme une expérience ayant changé de règles, pas une comparaison homogène depuis START.

## Choix autonome

Le modèle dispose de cinq outils en lecture seule : search_markets, browse_markets, get_market, search_web, read_web. Les recherches passent par le SDK officiel unifié, sont paginées et ne sont pas limitées à la liste initiale. L'agent choisit ses requêtes, sujets, marchés et sources. Il peut acheter un marché absent des douze marchés initialement suivis. Aucun filtre de liquidité ou d'échéance de la présélection initiale ne s'applique à ses recherches autonomes. Les restrictions techniques du protocole, les marchés fermés et les données indisponibles restent explicites.

Les sessions autonomes utilisent Azure Responses v1 avec store=false ; le SDK officiel transporte les appels d'outils et leurs résultats ainsi que les éléments de raisonnement nécessaires. L'ancien contrôle simple Chat Completions reste disponible pour les tests isolés. Cette adaptation est nécessaire pour les outils du déploiement GPT-6.1 Sol configuré : Chat Completions les refuse avec son mode de raisonnement.

L'univers n'est pas limité à quatre propositions. Le temps et les crédits restent bornés : trois tours d'outils, trois outils exécutés par tour, puis une décision ; quatre complétions Azure au maximum par session. Une recherche peut revenir vide : les prix et les faits ne sont jamais inventés.

La recherche web utilise GDELT DOC 2.0 et un secours Google News RSS sans clé commerciale. RSS est une interface de disponibilité non garantie. Les titres sont étiquetés comme tels ; ils ne valent pas confirmation d'un événement. read_web permet de consulter une source HTTPS publique, notamment officielle. Les contenus de pages sont des données non fiables, pas des instructions. Aucun contournement de paywall, certificat TLS, restriction géographique ou réseau privé n'est permis. Les résultats identiques sont mutualisés dans le cycle, jamais les décisions ou les portefeuilles.

## Profils

| Agents | Par position | Réserve | Par groupe | Pause de drawdown |
|---|---:|---:|---:|---:|
| A1 / A6 HUNTER libres | 100 % du liquide disponible | 0 % | aucune limite de prudence | aucune |
| A2 / A7 SPRINTER dynamiques | 75 % de la valeur liquidable | 5 % | 85 % | 85 %, une heure |
| Six autres agents | 35 % | 15 % | 55 % | 65 %, deux heures |

Les seuils obligatoires de confiance et d'avantage positif sont retirés. L'avantage est toujours recalculé et affiché. Un agent libre peut consciemment prendre une position à avantage estimé négatif : ce n'est pas un conseil d'investissement mais sa décision dans une compétition fictive. Les minimums de marché, frais, quantités disponibles, prix exécutables, ticks, données fraîches, absence d'emprunt et impossibilité de vendre des parts non détenues restent imposés. Les autres profils gardent leurs budgets explicites.

## Fréquences et coût

La fréquence activée reste de 12 sessions/jour pour chacun des quatre dynamiques, 4 pour chacun des six autres : maximum 72 sessions/jour, 504 sur sept jours. Une nouvelle recherche périodique peut déclencher une session même si les marchés déjà suivis n'ont pas bougé. La révision des règles permet une revue initiale, sans dépasser le quota journalier. Une session peut produire WAIT : aucune obligation de transaction.

| Scénario | Sessions/jour | Sessions/7 j | Complétions Azure maximales/7 j | Tokens de sortie maximaux/7 j |
|---|---:|---:|---:|---:|
| Ancien système | 72 | 504 | 504 | 806 400 |
| Autonomie v2 activée | 72 | 504 | 2 016 | 3 225 600 |
| Option 24/j dynamiques, 6/j standards, non activée | 132 | 924 | 3 696 | 5 913 600 |

Ces chiffres sont des plafonds de complétions réussies, pas une prévision de dépense. Les entrées, les tokens de raisonnement inclus dans les sorties et les éventuelles reprises influencent le coût. Aucun montant EUR/USD n'est inventé : le tarif réel dépend du modèle déployé, de la région et de l'offre Azure. Les tokens historiques v1 n'ont pas été enregistrés et ne peuvent pas être reconstruits.

Chaque session v2 journalise requests, model, prompt_tokens, completion_tokens et cached_prompt_tokens, même si sa décision échoue. Les totaux en base ne couvrent que les cycles validés : une annulation de transaction peut effacer leurs mesures sans annuler la facturation Azure. Les logs LLM_USAGE conservent désormais les mesures déjà obtenues avant une annulation ; les appels antérieurs sans ces logs et certaines reprises SDK restent non mesurés. La facturation Azure fait foi. `python -m survival.cli cost-report` affiche les mesures et les scénarios. Facultativement renseigner AZURE_INPUT_USD_PER_MILLION et AZURE_OUTPUT_USD_PER_MILLION avec les tarifs effectifs du compte pour obtenir une estimation USD conservatrice sans remise cache. Ces variables sont des valeurs de tarification, pas des secrets ; les ajouter au workflow si l'estimation doit être exécutée à distance. Les crédits restants ne sont pas connus de l'application.

Le job autorise 25 minutes afin de ne pas tuer un cycle pendant les recherches. Cela ne signifie pas qu'il dure 25 minutes. En dépôt privé, surveiller les minutes Actions réellement consommées et le blocage des dépassements. Les fournisseurs web ne facturent pas d'API commerciale ; les quotas et indisponibilités restent possibles. La fréquence supérieure n'est pas activée avant mesure.

## Diagnostic

Le dashboard affiche la fin du cycle, sa durée, le déclencheur GitHub, le lien de logs, la dernière exécution schedule effectivement constatée, les statuts de chaque agent et ses tokens mesurés. Il distingue WAIT/HOLD, NOT_DUE, EXECUTION_REJECTED, TECHNICAL_ERROR et PROVIDER_ERROR. La base conserve les recherches, leurs arguments, résultats, sources et erreurs dans system_events ; le dashboard en fournit une projection bornée.

Commandes : `python -m survival.cli research-check`, `health`, `cost-report`, `export`. Les mêmes commandes sont disponibles dans le workflow SURVIVAL cycles. research-check teste les recherches réelles sans démarrer une expérience ni créer d'opération.

Un statut GitHub vert ne suffit pas : consulter health, RESEARCH_ERROR et les décisions. Le heartbeat n'affiche une exécution automatique confirmée qu'après un vrai événement schedule. La cadence GitHub n'est pas garantie. Aucun journal synthétique n'est injecté dans l'expérience réelle.

Sources techniques : https://github.com/Polymarket/py-sdk ; https://docs.polymarket.com/api-reference/search/search-markets-events-and-profiles ; https://developers.openai.com/api/docs/guides/function-calling ; https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/ ; https://azure.microsoft.com/en-us/pricing/details/azure-openai/ .

## Validation en production du 13 octobre 2026

Le cycle [38316778029](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38316778029), terminé à 00:35:45 Paris, a relié Polymarket, les dix agents Azure, les recherches, Supabase et https://project-survival.pages.dev/. Durée 466,97 secondes, 21 marchés dont 9 hors collecte initiale, dix décisions WAIT valides, zéro rejet d'ordre et zéro erreur technique d'analyse. Les outils ont réussi 10 recherches de marchés, 10 recherches web, 12 inspections et 20 lectures de pages. Cinq autres appels d'outils ont échoué explicitement : certains sites et recherches restent indisponibles. Les traces complètes sont dans system_events.

Le contrôle [38317424623](https://github.com/arthurjanicaudschool/project-survival/actions/runs/38317424623) valide une deuxième page réelle du SDK, les carnets, huit résultats d'actualité et une lecture BBC. Les premières erreurs Azure et de clé étrangère ont été corrigées ; leurs journaux restent conservés. Les achats/ventes passent les tests déterministes et PostgreSQL ; aucun achat IA de papier n'est encore observé. START et l'échéance du 19 octobre à 22:36:07 Paris sont conservés.

Mesure : 40 complétions, 377 575 tokens d'entrée dont 101 669 en cache, 10 084 tokens de sortie, dix sessions. Tarifs fournis par l'utilisateur ; l'offre effective du déploiement reste à identifier :

| Offre | Dix sessions mesurées | Extrapolation 504 sessions / 7 j | Option 924 sessions / 7 j |
|---|---:|---:|---:|
| Court Global | 0,58 EUR | 29,41 EUR | 53,91 EUR |
| Court Data Zone | 0,70 EUR | 35,41 EUR | 64,92 EUR |
| Long Global | 1,12 EUR | 56,58 EUR | 103,73 EUR |
| Long Data Zone | 1,35 EUR | 68,00 EUR | 124,66 EUR |

Calcul : (entrées hors cache × tarif entrée + entrées en cache × tarif cache + sorties × tarif sortie) / 1 000 000. Les écritures de cache distinctement facturées sont exclues : leur nombre de tokens n'est pas exposé séparément. Ces extrapolations supposent le même coût moyen par session et tous les quotas utilisés. Ce ne sont ni une prévision fiable ni un plafond financier. Les cycles annulés, les appels historiques et certaines reprises SDK sont exclus ; la facture Azure fait foi. Le coût historique v1 est inconnu. Tarifs configurables dans config/azure_pricing_eur.json ; cost-report calcule les quatre offres.

Point encore non confirmé : aucun événement GitHub schedule observé malgré un workflow actif sur main. Les lancements ci-dessus sont manuels. Le cron a été réenregistré et le workflow réactivé ; seul un vrai cycle schedule permettra de déclarer l'autonomie PC éteint vérifiée. Le dashboard indique cette absence de preuve. GitHub Status indiquait Actions opérationnel lors de l'inspection ; aucune cause certaine n'est établie.
