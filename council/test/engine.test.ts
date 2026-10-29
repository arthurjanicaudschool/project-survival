import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Engine} from '../src/engine';
import {book,market,repository,env} from './helpers';
import {nextSlots} from '../src/schedule';
const analysis={speech:'Je propose une mise utile, justifiée par les informations vérifiées du dossier.',recommendation:'PROPOSE',estimated_yes_probability:.68,confidence:.7,side:'YES',amount:'100',max_price:'.55',reasoning:'Les données vérifiées rendent ce pari intéressant à ce prix, avec une incertitude réelle.',uncertainty:'Le résultat reste incertain.',citations:[],urgent:false,urgency_reason:'',lesson:'',document_requests:[]};
function setup(options:{missing?:string[];abstain?:string[];amend?:boolean;reject?:boolean}={}){
  const r=repository(),m=market();let settled=false;
  const markets={synthetic:true,fx:async()=>({usd_per_eur:'1.1',reference_date:'2026-10-29',source:'fixture',method:'demo only'}),catalog:async()=>[],evidence:async()=>[],inspect:async()=>({...m,books:{YES:book(),NO:book()},resolved:settled,payouts:settled?{YES:'1',NO:'0'}:null,resolution_evidence:settled?{fixture:true}:null})};
  const azure={synthetic:true,ask:async(id:string,actor:string,phase:string,c:any)=>{
    if(options.missing?.includes(actor))throw Error('AZURE_TIMEOUT');
    if(phase==='independent_analysis')return analysis;
    if(phase==='discussion'||phase==='rebuttal')return {speech:'Je confronte la proposition aux données disponibles et souligne une incertitude concrète.',estimated_yes_probability:.64,objection:'Une incertitude mesurée demeure.',amendment:null,citations:[],document_requests:[]};
    if(phase==='chair_question_and_amendment')return {speech:'Nous avons entendu les objections. Nous votons maintenant sur une proposition précise.',question:'',question_to:null,amendment:options.amend?{market_id:m.id,side:'NO',amount:'150',max_price:'.6',reason:'Le débat justifie un changement de côté et de montant.'}:null,document_requests:[]};
    if(phase==='tie_arbitration')return {decision:'CANCEL',speech:'Je prends du recul et annule cette proposition malgré mon premier avis favorable.',proposal_id:c.proposal.id,proposal_version:c.proposal.version};
    const abstain=options.abstain?.includes(actor),against=options.reject||['RISK','CONTRA'].includes(actor)&&options.abstain?.length;
    return {vote:abstain?'ABSTAIN':against?'AGAINST':'FOR',speech:'Ma position est réfléchie et tient compte du montant, des données et de l’incertitude.',abstention_reason:abstain?'Information essentielle impossible à vérifier dans le délai actuel.':'',reconsider_if:abstain?'Publication officielle de cette information.':'',proposal_id:c.proposal.id,proposal_version:c.proposal.version};
  }};
  const e=new Engine(r,env,markets as any,azure as any);e.prepare('test','demo');
  return {r,e,m,settle:()=>{settled=true;}};
}
async function drain(e:Engine){for(let i=0;i<20;i++){const j=e.repo.claim();if(!j)return;await e.process(j);e.repo.complete(j);}}
async function startCouncil(s:ReturnType<typeof setup>){await s.e.start();s.r.run("UPDATE jobs SET status='DONE'");s.r.putMarket(s.m);s.r.putDossier({id:s.m.id,market_id:s.m.id,category:s.m.category,status:'PENDING',priority:50,hash:'fixture',payload:{source_ids:[]}});await s.e.analyze(s.m.id);await s.e.slot('fixture-slot','EXTRAORDINARY');await drain(s.e);}
test('full demo chain: individual analysis, contradiction, chair, five votes, buy, resolution, EUR P&L',async()=>{
  const s=setup();await startCouncil(s);assert.equal(s.r.one('SELECT count(*) n FROM votes').n,5);assert.equal(s.r.one('SELECT count(*) n FROM positions').n,1);assert.equal(s.r.cash(),'1000');assert.equal(s.r.meeting('meeting:fixture-slot').status,'COMPLETED');s.settle();await s.e.settlements();assert.equal(s.r.cash(),'1200');assert.equal(s.e.summary().profit_eur,'90.90909090909090909090909090909090909091');await s.e.settlements();assert.equal(s.r.cash(),'1200');assert.equal(s.r.one('SELECT count(*) n FROM ledger').n,3);
});
test('amended side and stake voted on latest version only',async()=>{const s=setup({amend:true});await startCouncil(s);const p=s.r.one('SELECT * FROM positions');assert.equal(p.outcome,'NO');assert.equal(p.cost,'150');const versions=s.r.rows('SELECT DISTINCT version FROM votes');assert.deepEqual(versions.map(v=>v.version),[2]);});
test('two abstentions cannot produce a low-turnout purchase',async()=>{const s=setup({abstain:['QUANT','RISK']});await startCouncil(s);assert.equal(s.r.one('SELECT count(*) n FROM positions').n,0);assert.equal(s.r.proposal('meeting:fixture-slot:market1')?.status,'POSTPONE');});
test('tied vote asks abstainer again then chair may cancel',async()=>{const s=setup({abstain:['FOOTBALL']});await startCouncil(s);assert.equal(s.r.one('SELECT count(*) n FROM positions').n,0);assert.equal(s.r.proposal('meeting:fixture-slot:market1')?.status,'CANCEL');assert.equal(s.r.one('SELECT count(*) n FROM votes WHERE round=2').n,1);assert.ok(s.r.one("SELECT id FROM events WHERE kind='ARBITRATION'"));});
test('rejection records executable hypothetical ten EUR without changing cash',async()=>{const s=setup({reject:true});await startCouncil(s);assert.equal(s.r.cash(),'1100');const c=JSON.parse(s.r.one('SELECT payload FROM counterfactuals').payload);assert.equal(c.execution.spent,'11');s.settle();await s.e.settlements();assert.equal(s.r.cash(),'1100');assert.equal(JSON.parse(s.r.one('SELECT payload FROM counterfactuals').payload).profit,'11');});
test('resume the exact execution stage cannot buy twice',async()=>{const s=setup();await startCouncil(s);const m=s.r.meeting('meeting:fixture-slot');m.status='RUNNING';m.stage='EXECUTE';m.payload.index=0;s.r.putMeeting(m);await s.e.advance(m.id);assert.equal(s.r.one('SELECT count(*) n FROM positions').n,1);assert.equal(s.r.cash(),'1000');});
test('no agenda publishes a bulletin without AI or fabricated speeches',async()=>{const s=setup();await s.e.start();await s.e.slot(nextSlots(new Date().toISOString(),null,1)[0],'ORDINARY');assert.equal(s.r.one('SELECT status FROM meetings').status,'NO_AGENDA');assert.equal(s.r.one('SELECT count(*) n FROM events WHERE kind=?','SPEECH').n,0);});
