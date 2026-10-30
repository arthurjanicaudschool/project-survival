import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {D,execute} from '../src/finance';
test('100 cases agree with the independent Python Decimal paper engine',()=>{
  const cases=JSON.parse(readFileSync(new URL('./decimal-parity.json',import.meta.url),'utf8'));
  for(const c of cases){const e=execute(c.book,c.budget,c.limit,c.at);assert.equal(e.status,c.expected.status,c.book.evidence);assert.equal(e.reason,c.expected.reason||'',c.book.evidence);for(const field of ['quantity','gross','fees','spent'])assert.ok(D((e as any)[field]).eq(c.expected[field]),c.book.evidence+':'+field);assert.equal(e.fills.length,c.expected.fills.length);for(let i=0;i<e.fills.length;i++)for(const field of ['price','quantity','fee'])assert.ok(D((e.fills[i] as any)[field]).eq(c.expected.fills[i][field]),c.book.evidence+':fill:'+field);}
});
