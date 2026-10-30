import { z } from 'zod';

export const CATEGORIES = ['weather','football','basketball','tennis','esport'] as const;
export type Category = typeof CATEGORIES[number];
export const MEMBERS = [
  {id:'WEATHER',name:'Thomas Morel',role:'Météo',category:'weather',personality:'Météorologue probabiliste. Relie station, horizon et erreur historique ; ne transforme pas une prévision ponctuelle en certitude.'},
  {id:'FOOTBALL',name:'Sofia Laurent',role:'Football',category:'football',personality:'Analyste des équipes et calendriers. Compare forme, effectifs disponibles et règles exactes de règlement.'},
  {id:'BASKETBALL',name:'Malik Bennett',role:'Basketball',category:'basketball',personality:'Analyste des possessions, rotations et blessures. Sépare données établies et informations non confirmées.'},
  {id:'TENNIS',name:'Elena Varga',role:'Tennis',category:'tennis',personality:'Analyse surface, format, joueurs, fatigue et forfaits. Accepte une incertitude mesurée et propose une mise utile.'},
  {id:'ESPORT',name:'Alex Chen',role:'Esport',category:'esport',personality:'Analyse jeu, format, roster et cartes. Vérifie les noms et horaires plutôt que de déduire la force des seuls prix.'},
  {id:'QUANT',name:'Gabriel Weiss',role:'Quant',personality:'Quantitatif indépendant. Vérifie probabilités, prix tout compris et scénarios. Propose des ajustements chiffrés plutôt que des réserves vagues.'},
  {id:'RISK',name:'Nadia Diallo',role:'Risk Manager',personality:'Analyse exposition et conséquences des pertes. Aucun veto personnel : seul le contrôle technique du backend bloque. Propose une alternative investissable.'},
  {id:'CONTRA',name:'Victor Shaw',role:'Contradicteur',personality:'Cherche le meilleur argument contraire et les hypothèses fragiles. Un désaccord doit aider à décider, pas bloquer systématiquement.'},
  {id:'CHAIR',name:'Claire Beaumont',role:'Chairman',personality:'Préside, fait avancer les échanges et recherche une décision réfléchie. Peut changer d’avis. Aucun achat sans vote valide ou arbitrage autorisé.'},
  {id:'SECRETARY',name:'Camille Rousseau',role:'Secrétaire',personality:'Archive et retrouve les documents avec leurs références. Aucun vote, aucune probabilité inventée.'},
] as const;
export type MemberId = typeof MEMBERS[number]['id'];
export const CONFIG = {
  durationHours:168, settlementBufferHours:6, initialEur:'1000', scanMinutes:10,
  meetingHours:[9,13,17,21], maxMeetingSeconds:600, maxAgenda:3,
  emergencyCooldownMinutes:45, emergencyMaxPerDay:4, analysisCooldownMinutes:120,
  fetchTimeoutMs:15000, azureTimeoutMs:75000, azureAttempts:2, maxContextChars:26000,
  maxOutputTokens:1800, maxBookAgeSeconds:180, documentChars:9000,
  transientCacheHours:12, quotaWarningBytes:250_000_000, version:'survival-phase3-v1',
};
export type Env = {
  COUNCIL:DurableObjectNamespace; EXPERIMENT_ID:string; AZURE_DEPLOYMENT:string;
  AZURE_ENDPOINT?:string; AZURE_KEY?:string; ADMIN_TOKEN?:string;
  PUBLIC_ORIGIN:string; ALLOW_FIXTURES?:string; NTFY_TOPIC?:string; NTFY_TOKEN?:string; NTFY_DELIVERY?:string; GITHUB_NOTIFIER_TOKEN?:string;
};
export type Book = {asset_id:string; observed_at:string;exchange_at?:string; bids:{price:string;size:string}[]; asks:{price:string;size:string}[]; minimum:string;tick:string;fee_rate:string;fee_exponent:string;evidence:string};
export type Source = {id:string;url:string;title:string;text:string;fetched_at:string;status:'VERIFIED'|'UNAVAILABLE';provider:string};
export type Market = {id:string;question:string;event_title?:string;description:string;category:Category;url:string;group:string;version:'v1'|'v2';condition_id:string|null;question_id:string|null;assets:{YES:string;NO:string};outcome_labels?:{YES:string;NO:string};start_at:string|null;end_at:string;event_end_at:string;resolution_source:string;active:boolean;resolved:boolean;payouts:{YES:string;NO:string}|null;resolution_evidence:Record<string,unknown>|null;liquidity:string;volume:string;books:Partial<Record<'YES'|'NO',Book>>;delay_seconds:number;observed_at:string;tags:string[]};
export type Proposal = {id:string;meeting_id:string;market_id:string;version:number;side:'YES'|'NO';amount:string;max_price:string;status:string;reason:string;created_at:string};
export type State = {id:string;mode:'live'|'demo'|'validation';status:'READY'|'RUNNING'|'CLOSING'|'FINISHED';started_at:string|null;end_at:string|null;betting_deadline:string|null;fx:{usd_per_eur:string;reference_date:string;source:string;method:string}|null;initial_eur:string;created_at:string;updated_at:string;last_scan:string|null;last_cycle:string|null;emergency_day:string;emergency_count:number;last_emergency:string|null;last_error:string|null};
export const decimalString=z.string().regex(/^\d+(?:\.\d+)?$/).max(28);
const nullableDecimal=decimalString.nullable();
const citation=z.object({source_id:z.string().max(100),quote:z.string().min(12).max(240)}).strict();
export const AnalysisSchema=z.object({
  speech:z.string().min(30).max(1800), recommendation:z.enum(['PROPOSE','WAIT']),
  estimated_yes_probability:z.number().min(0).max(1).nullable(), confidence:z.number().min(0).max(1),
  side:z.enum(['YES','NO']).nullable(), amount:nullableDecimal,max_price:nullableDecimal,
  reasoning:z.string().min(20).max(1600), uncertainty:z.string().max(800),
  citations:z.array(citation).max(5), urgent:z.boolean(), urgency_reason:z.string().max(400),
  lesson:z.string().max(600),document_requests:z.array(z.string().min(3).max(160)).max(2),
}).strict();
export type Analysis=z.infer<typeof AnalysisSchema>;
export const SpeechSchema=z.object({speech:z.string().min(20).max(1800),estimated_yes_probability:z.number().min(0).max(1).nullable(),
  objection:z.string().max(700),amendment:z.object({market_id:z.string(),side:z.enum(['YES','NO']),amount:decimalString,max_price:decimalString,reason:z.string().min(15).max(700)}).strict().nullable(),
  citations:z.array(citation).max(4),document_requests:z.array(z.string().min(3).max(160)).max(2),
}).strict();
export const ChairSchema=z.object({speech:z.string().min(20).max(1800),question:z.string().max(600),question_to:z.string().max(30).nullable(),
  amendment:z.object({market_id:z.string(),side:z.enum(['YES','NO']),amount:decimalString,max_price:decimalString,reason:z.string().min(15).max(700)}).strict().nullable(),document_requests:z.array(z.string().min(3).max(160)).max(2)}).strict();
export const VoteSchema=z.object({vote:z.enum(['FOR','AGAINST','ABSTAIN']),speech:z.string().min(25).max(1100),
  abstention_reason:z.string().max(700),reconsider_if:z.string().max(500),proposal_id:z.string(),proposal_version:z.number().int().positive()}).strict();
export type Vote=z.infer<typeof VoteSchema> & {member_id:MemberId};
export const ArbitrationSchema=z.object({decision:z.enum(['APPROVE','REJECT','CANCEL']),speech:z.string().min(40).max(1600),proposal_id:z.string(),proposal_version:z.number().int().positive()}).strict();
export function panel(category:Category):MemberId[]{return [category.toUpperCase() as MemberId,'QUANT','RISK','CONTRA','CHAIR'];}
export function member(id:string){return MEMBERS.find(m=>m.id===id)!;}
export function now(){return new Date().toISOString();}
export function reasonLabel(code:string){return ({STALE_BOOK:'Les prix sont trop anciens.',BELOW_MARKET_MINIMUM:'La quantité proposée est sous le minimum réel.',NO_LIQUIDITY:'Aucune quantité achetable.',PRICE_LIMIT:'Le prix dépasse la limite votée.',INSUFFICIENT_CASH:'Le fonds ne dispose pas de cette somme.',OUTSIDE_WINDOW:'Le calendrier sort de la fenêtre autorisée.',ALREADY_INVESTED:'Un pari existe déjà sur ce marché.',UNKNOWN_FEES:'Les frais ne sont pas vérifiés.',INVALID_TICK_IN_BOOK:'Le carnet ne respecte pas le pas de prix.',UNKNOWN_TIMING:'La fin réelle de l’événement n’est pas vérifiée.'} as Record<string,string>)[code]||code;}
