import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/data-cache.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText;
const {cacheConfirmed, readConfirmed, connectionError} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const values = new Map();
globalThis.localStorage = {getItem:k=>values.get(k) || null, setItem:(k,v)=>values.set(k,v)};
const state = {id:"survival-002", mode:"live", updated_at:"2026-10-28T17:43:18Z", agents:[], fx:{usd_per_eur:"1.1"}, markets:{}};

test("confirmed cache survives refresh and stays isolated by experiment", () => {
  cacheConfirmed(state.id, state);
  assert.deepEqual(readConfirmed(state.id), state);
  assert.equal(readConfirmed("survival-001"), null);
});

test("demo, wrong experiment and invalid timestamp cannot replace genuine data", () => {
  for (const changes of [{mode:"demo"}, {id:"survival-001"}, {updated_at:"invalid"}]) {
    cacheConfirmed(state.id, {...state, ...changes});
    assert.deepEqual(readConfirmed(state.id), state);
  }
});

test("corrupt or disabled local storage does not prevent connecting", () => {
  values.set("survival:confirmed:corrupt", "{");
  assert.equal(readConfirmed("corrupt"), null);
  const storage = globalThis.localStorage;
  globalThis.localStorage = {getItem(){throw Error("disabled");},setItem(){throw Error("full");}};
  assert.equal(readConfirmed(state.id), null);
  assert.doesNotThrow(()=>cacheConfirmed(state.id, state));
  globalThis.localStorage = storage;
});

test("connection failures distinguish timeout and actual quota restriction", () => {
  assert.match(connectionError({}, true), /délai/);
  assert.match(connectionError({status:402}, false), /quota/);
  assert.doesNotMatch(connectionError({message:"upstream unavailable"}, false), /quota/);
});
