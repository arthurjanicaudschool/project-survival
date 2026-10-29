import {test} from 'node:test';
import assert from 'node:assert/strict';
import {tick} from './worker.js';

async function scenario(state,dispatchStatus=204) {
  const original=globalThis.fetch;const calls=[];
  globalThis.fetch=async (url,options)=>{
    calls.push({url,options});
    return calls.length===1 ? Response.json([state]) : new Response(null,{status:dispatchStatus});
  };
  try{return {result:await tick({SUPABASE_URL:'https://example.org',SUPABASE_ANON_KEY:'public-test',EXPERIMENT_ID:'fixture',GITHUB_REPOSITORY:'test/fixture',GITHUB_SCHEDULER_TOKEN:'not-a-real-token'}),calls};}
  finally{globalThis.fetch=original;}
}
test('fresh state does not dispatch',async()=>{
  const {result,calls}=await scenario({status:'RUNNING',updated_at:new Date().toISOString()});
  assert.equal(result.status,'FRESH');assert.equal(calls.length,1);
});
test('overdue state dispatches the paper cycle with true provenance',async()=>{
  const {result,calls}=await scenario({status:'RUNNING',updated_at:new Date(Date.now()-15*60000).toISOString()});
  assert.equal(result.event,'paper_cycle_dispatched');assert.equal(calls.length,2);
  assert.equal(JSON.parse(calls[1].options.body).inputs.source,'cloudflare-watchdog');
  assert.equal(JSON.parse(calls[1].options.body).inputs.action,'cycle');
  assert.equal(JSON.parse(calls[1].options.body).inputs.experiment,'fixture');
});
test('fresh in-progress cycle is not interrupted',async()=>{
  const {result,calls}=await scenario({status:'RUNNING',inflight:{id:'fixture'},updated_at:new Date(Date.now()-15*60000).toISOString()});
  assert.equal(result.status,'FRESH');assert.equal(calls.length,1);
});
test('finished experiment does not dispatch',async()=>{
  const {result,calls}=await scenario({status:'FINISHED'});assert.equal(result.status,'INACTIVE');assert.equal(calls.length,1);
});
test('prepared phase 2 never dispatches before START',async()=>{
  const {result,calls}=await scenario({status:'READY',started_at:null,end_at:null});assert.equal(result.status,'INACTIVE');assert.equal(calls.length,1);
});
test('dispatch rejection is an error, not success',async()=>{
  await assert.rejects(()=>scenario({status:'RUNNING',updated_at:new Date(Date.now()-20*60000).toISOString()},403),/Dispatch failed: 403/);
});
