import {DatabaseSync} from 'node:sqlite';
import {Repository} from '../src/repository';
import type {Book,Market,Proposal,Env} from '../src/domain';
export function repository(){
  const db=new DatabaseSync(':memory:');
  const sql={exec(q:string,...args:any[]){const s=db.prepare(q);const isRead=s.columns().length>0;const rows=isRead?s.all(...args):[];const info=isRead?null:s.run(...args);return {toArray:()=>rows,rowsRead:rows.length,rowsWritten:Number(info?.changes||0)};},get databaseSize(){return 4096;}};
  return new Repository(sql,f=>{db.exec('BEGIN');try{const r=f();db.exec('COMMIT');return r;}catch(e){db.exec('ROLLBACK');throw e;}});
}
export const env={EXPERIMENT_ID:'test',AZURE_DEPLOYMENT:'gpt-6.1-sol-3',PUBLIC_ORIGIN:'http://localhost:5173',ALLOW_FIXTURES:'false'} as Env;
export function book():Book{return {asset_id:'tokenYES',observed_at:new Date().toISOString(),bids:[{price:'.49',size:'1000'}],asks:[{price:'.5',size:'1000'}],minimum:'5',tick:'.01',fee_rate:'0',fee_exponent:'1',evidence:'observed-hash'};}
export function market():Market{return {id:'market1',question:'Team A gagne-t-elle ?',description:'Règles officielles du match.',category:'football',url:'https://polymarket.com/event/test',group:'event1',version:'v1',condition_id:'condition',question_id:null,assets:{YES:'tokenYES',NO:'tokenNO'},start_at:new Date(Date.now()+86400000).toISOString(),end_at:new Date(Date.now()+2*86400000).toISOString(),event_end_at:new Date(Date.now()+2*86400000).toISOString(),resolution_source:'https://espn.com',active:true,resolved:false,payouts:null,resolution_evidence:null,liquidity:'100000',volume:'10000',books:{YES:book(),NO:{...book(),asset_id:'tokenNO'}},delay_seconds:0,observed_at:new Date().toISOString(),tags:['soccer']};}
export function proposal():Proposal{return {id:'p1',meeting_id:'meeting1',market_id:'market1',version:1,side:'YES',amount:'100',max_price:'.55',status:'APPROVED',reason:'Analyse vérifiée des données disponibles.',created_at:new Date().toISOString()};}
