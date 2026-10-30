import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const publicFile=name=>new URL('../public/'+name,import.meta.url);
test('both historic dashboards retain the exact verified final projection',()=>{
  const manifest=JSON.parse(readFileSync(publicFile('archive-manifest.json'),'utf8'));
  for(const item of manifest.archives){const bytes=readFileSync(publicFile(item.file)),state=JSON.parse(bytes);assert.equal(createHash('sha256').update(bytes).digest('hex'),item.sha256);assert.equal(bytes.length,item.bytes);assert.equal(state.id,item.experiment_id);assert.equal(state.status,'FINISHED');assert.equal(state.mode,'live');assert.equal(Object.keys(state.agents).length,10);assert.equal(state.archive.experiment_id,item.experiment_id);}
});
test('phase 3 example is explicitly a separate archived rehearsal',()=>{
  const d=JSON.parse(readFileSync(publicFile('demo-phase3.json'),'utf8'));
  assert.equal(d.summary.state.mode,'demo');assert.equal(d.summary.state.status,'REPLAY');assert.equal(d.provenance.production_experiment_started,false);assert.notEqual(d.summary.state.id,'survival-003');assert.equal(d.summary.positions.length,1);assert.equal(d.summary.positions[0].cost,'84.999');assert.ok(d.events.some(e=>e.kind==='VOTES'));assert.ok(d.events.some(e=>e.kind==='BET'));
});
