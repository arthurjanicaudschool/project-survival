import {CONFIG,now,type State,type Proposal,type Source} from './domain';
import {D,type Execution} from './finance';

export interface SqlLike {exec(query:string,...bindings:any[]):any;databaseSize?:number;}
export class Repository {
  reads=0;writes=0;
  constructor(public sql:SqlLike,public atomic:<T>(f:()=>T)=>T){this.migrate();}
  rows<T=any>(q:string,...args:any[]):T[]{const c=this.sql.exec(q,...args);const r=c.toArray();this.reads+=c.rowsRead||0;this.writes+=c.rowsWritten||0;return r;}
  one<T=any>(q:string,...args:any[]):T|undefined{return this.rows<T>(q,...args)[0];}
  run(q:string,...args:any[]){this.rows(q,...args);}
  migrate(){for(const q of [
    'CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,url TEXT NOT NULL,title TEXT NOT NULL,text TEXT NOT NULL,fetched_at TEXT NOT NULL,provider TEXT NOT NULL,status TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS markets(id TEXT PRIMARY KEY,category TEXT NOT NULL,updated_at TEXT NOT NULL,payload TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS dossiers(id TEXT PRIMARY KEY,market_id TEXT NOT NULL,category TEXT NOT NULL,status TEXT NOT NULL,priority REAL NOT NULL,hash TEXT NOT NULL,updated_at TEXT NOT NULL,payload TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS dossiers_status ON dossiers(status,priority)',
    'CREATE TABLE IF NOT EXISTS meetings(id TEXT PRIMARY KEY,slot TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL,created_at TEXT NOT NULL,started_at TEXT,finished_at TEXT,payload TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS proposals(id TEXT NOT NULL,version INTEGER NOT NULL,meeting_id TEXT NOT NULL,market_id TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(id,version))',
    'CREATE TABLE IF NOT EXISTS votes(proposal_id TEXT NOT NULL,version INTEGER NOT NULL,round INTEGER NOT NULL,member_id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(proposal_id,version,round,member_id))',
    'CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,at TEXT NOT NULL,meeting_id TEXT,kind TEXT NOT NULL,actor TEXT NOT NULL,text TEXT NOT NULL,details TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS events_meeting ON events(meeting_id,seq)',
    'CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY,at TEXT NOT NULL,kind TEXT NOT NULL,amount TEXT NOT NULL,reference TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS positions(id TEXT PRIMARY KEY,market_id TEXT NOT NULL UNIQUE,outcome TEXT NOT NULL,status TEXT NOT NULL,cost TEXT NOT NULL,quantity TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS fills(id TEXT PRIMARY KEY,position_id TEXT NOT NULL,asset_id TEXT NOT NULL,book_hash TEXT NOT NULL,price TEXT NOT NULL,quantity TEXT NOT NULL,fee TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS fills_book ON fills(asset_id,book_hash)',
    'CREATE TABLE IF NOT EXISTS counterfactuals(id TEXT PRIMARY KEY,market_id TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,due_at TEXT NOT NULL,status TEXT NOT NULL,lease_until TEXT,payload TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,error TEXT)',
    'CREATE INDEX IF NOT EXISTS jobs_due ON jobs(status,due_at)',
    'CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,actor TEXT NOT NULL,meeting_id TEXT,created_at TEXT NOT NULL,status TEXT NOT NULL,input_tokens INTEGER NOT NULL DEFAULT 0,output_tokens INTEGER NOT NULL DEFAULT 0,cached_tokens INTEGER NOT NULL DEFAULT 0,cache_write_tokens INTEGER NOT NULL DEFAULT 0,estimated_eur TEXT,result TEXT,error TEXT)',
    'CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,status TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,payload TEXT NOT NULL,error TEXT)',
    'CREATE TABLE IF NOT EXISTS transient_cache(key TEXT PRIMARY KEY,expires_at TEXT NOT NULL,payload TEXT NOT NULL)',
    "CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_LEDGER'); END",
    "CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_LEDGER'); END",
  ])this.run(q);}
  proof(book:any){const id='book:'+book.asset_id+':'+book.evidence;this.run('INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,?,?)',id,'https://clob.polymarket.com/book?token_id='+encodeURIComponent(book.asset_id),'Carnet observé — preuve de simulation',JSON.stringify(book),book.observed_at,'Polymarket','VERIFIED');return id;}
  get<T=any>(key:string):T|null{const r=this.one('SELECT value FROM meta WHERE key=?',key);return r?JSON.parse(r.value):null;}
  set(key:string,value:unknown){this.run('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',key,JSON.stringify(value));}
  state(){return this.get<State>('state');}
  save(s:State){s.updated_at=now();this.set('state',s);}
  event(id:string,kind:string,text:string,actor='SECRETARY',meeting:string|null=null,details:unknown={}){
    this.run('INSERT OR IGNORE INTO events(id,at,meeting_id,kind,actor,text,details) VALUES(?,?,?,?,?,?,?)',id,now(),meeting,kind,actor,text,JSON.stringify(details));
    return this.one('SELECT * FROM events WHERE id=?',id);
  }
  events(after=0,meeting?:string,limit=100){
    return (meeting?this.rows('SELECT * FROM events WHERE meeting_id=? AND seq>? ORDER BY seq LIMIT ?',meeting,after,limit):this.rows('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?',after,limit)).map(r=>({...r,details:JSON.parse(r.details)}));
  }
  document(s:Source){this.run('INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,?,?)',s.id,s.url,s.title,s.text.slice(0,CONFIG.documentChars),s.fetched_at,s.provider,s.status);}
  retrieve(query:string,limit=3):Source[]{
    const terms=query.toLowerCase().split(/\W+/).filter(s=>s.length>=3).slice(0,6);
    if(!terms.length)return [];
    const where=terms.map(()=>'(lower(title) LIKE ? OR lower(text) LIKE ?)').join(' OR ');
    const documents=this.rows(`SELECT * FROM documents WHERE status='VERIFIED' AND id NOT LIKE 'book:%' AND (${where}) ORDER BY fetched_at DESC LIMIT ?`,...terms.flatMap(t=>[`%${t}%`,`%${t}%`]),limit);
    const history=this.rows(`SELECT * FROM events WHERE kind IN ('SPEECH','LESSON','SETTLEMENT','DECISION','ARBITRATION','MEETING_END') AND (${terms.map(()=>'(lower(text) LIKE ? OR lower(details) LIKE ?)').join(' OR ')}) ORDER BY seq DESC LIMIT ?`,...terms.flatMap(t=>[`%${t}%`,`%${t}%`]),limit);
    const past=history.map(e=>({id:'memory:'+e.seq,url:'https://project-survival.pages.dev/?phase=3&meeting='+encodeURIComponent(e.meeting_id||''),title:`Archive ${e.at} — ${e.actor} — ${e.kind}`,text:e.text+'\n'+e.details,fetched_at:e.at,provider:'Council archive',status:'VERIFIED' as const}));
    for(const d of past)this.document(d);
    return [...past.slice(0,1),...documents,...past.slice(1)].slice(0,limit);
  }
  dossier(id:string){const r=this.one('SELECT * FROM dossiers WHERE id=?',id);return r?{...r,payload:JSON.parse(r.payload)}:null;}
  market(id:string){const r=this.one('SELECT payload FROM markets WHERE id=?',id);return r?JSON.parse(r.payload):null;}
  putMarket(m:any){this.run('INSERT INTO markets VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET category=excluded.category,updated_at=excluded.updated_at,payload=excluded.payload',m.id,m.category,now(),JSON.stringify(m));}
  putDossier(d:any){this.run('INSERT INTO dossiers VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,priority=excluded.priority,hash=excluded.hash,updated_at=excluded.updated_at,payload=excluded.payload',d.id,d.market_id,d.category,d.status,d.priority,d.hash,now(),JSON.stringify(d.payload));}
  meeting(id:string){const r=this.one('SELECT * FROM meetings WHERE id=?',id);return r?{...r,payload:JSON.parse(r.payload)}:null;}
  putMeeting(m:any){this.run('INSERT INTO meetings VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,stage=excluded.stage,started_at=excluded.started_at,finished_at=excluded.finished_at,payload=excluded.payload',m.id,m.slot,m.kind,m.status,m.stage,m.created_at,m.started_at||null,m.finished_at||null,JSON.stringify(m.payload));}
  proposal(id:string,version?:number):Proposal|null{const r=version?this.one('SELECT payload FROM proposals WHERE id=? AND version=?',id,version):this.one('SELECT payload FROM proposals WHERE id=? ORDER BY version DESC LIMIT 1',id);return r?JSON.parse(r.payload):null;}
  putProposal(p:Proposal){this.run('INSERT INTO proposals VALUES(?,?,?,?,?,?) ON CONFLICT(id,version) DO UPDATE SET status=excluded.status,payload=excluded.payload',p.id,p.version,p.meeting_id,p.market_id,p.status,JSON.stringify(p));}
  enqueue(id:string,kind:string,payload:unknown,due=now()){
    this.run("INSERT OR IGNORE INTO jobs(id,kind,due_at,status,payload) VALUES(?,?,?,'PENDING',?)",id,kind,due,JSON.stringify(payload));
  }
  claim(at=now()):any|null{return this.atomic(()=>{
    const job=this.one("SELECT * FROM jobs WHERE (status='PENDING' AND due_at<=?) OR (status='RUNNING' AND lease_until<?) ORDER BY CASE kind WHEN 'MEETING' THEN 0 WHEN 'SLOT' THEN 1 WHEN 'EMERGENCY' THEN 1 WHEN 'NOTIFY' THEN 2 WHEN 'SETTLE' THEN 3 ELSE 4 END,due_at LIMIT 1",at,at);
    if(!job)return null;
    const lease=new Date(Date.parse(at)+660000).toISOString();
    this.run("UPDATE jobs SET status='RUNNING',lease_until=?,attempt=attempt+1 WHERE id=?",lease,job.id);
    return {...job,lease_until:lease,attempt:job.attempt+1,payload:JSON.parse(job.payload)};
  });}
  complete(job:any){this.run("UPDATE jobs SET status='DONE',lease_until=NULL WHERE id=? AND lease_until=?",job.id,job.lease_until);}
  retry(job:any,error:string,seconds=30){this.run("UPDATE jobs SET status='PENDING',lease_until=NULL,due_at=?,error=? WHERE id=? AND lease_until=?",new Date(Date.now()+seconds*1000).toISOString(),error.slice(0,240),job.id,job.lease_until);}
  cash(){return this.rows('SELECT amount FROM ledger').reduce((n,r)=>n.plus(r.amount),D(0)).toFixed();}
  consumed(asset:string,hash:string){const result:Record<string,string>={};for(const f of this.rows('SELECT price,quantity FROM fills WHERE asset_id=? AND book_hash=?',asset,hash))result[f.price]=D(result[f.price]||0).plus(f.quantity).toFixed();return result;}
  buy(p:Proposal,m:any,e:Execution,reason:string){return this.atomic(()=>{
    const id=`${p.id}:v${p.version}`;
    if(this.one('SELECT id FROM positions WHERE id=?',id))return {id,duplicate:true};
    if(this.one('SELECT id FROM positions WHERE market_id=?',m.id))throw Error('ALREADY_INVESTED');
    if(!e.fills.length||D(e.spent).gt(this.cash()))throw Error('INSUFFICIENT_CASH');
    this.run('INSERT INTO ledger VALUES(?,?,?,?,?)',id+':buy',now(),'BUY',D(e.spent).neg().toFixed(),id);
    const proof=this.proof(m.books[p.side]);
    const probability=this.dossier(m.id)?.payload?.analysis?.estimated_yes_probability??null;
    const position={proposal:p,question:m.question,url:m.url,category:m.category,end_at:m.event_end_at,estimated_yes_probability:probability,expected_edge_per_share:probability===null?null:D(p.side==='YES'?probability:D(1).minus(probability)).minus(D(e.spent).div(e.quantity)).toFixed(),reason,fees:e.fees,market_version:m.version,book_proof:proof,outcome_label:m.outcome_labels?.[p.side]||p.side};
    this.run("INSERT INTO positions VALUES(?,?,?,'PENDING',?,?,?,?)",id,m.id,p.side,e.spent,e.quantity,now(),JSON.stringify(position));
    e.fills.forEach((f,i)=>this.run('INSERT INTO fills VALUES(?,?,?,?,?,?,?)',`${id}:${i}`,id,m.assets[p.side],m.books[p.side].evidence,f.price,f.quantity,f.fee));
    this.event(id+':fill','BET',`Le conseil a misé ${e.spent} unités de cotation sur ${p.side==='YES'?'Oui':'Non'}.`,'SECRETARY',p.meeting_id,{position_id:id,execution:e,proposal:p});
    return {id,duplicate:false};
  });}
  settle(position:any,m:any){return this.atomic(()=>{
    const current=this.one('SELECT * FROM positions WHERE id=?',position.id);
    if(!current||current.status==='SETTLED')return false;
    if(!m.resolved||!m.payouts)throw Error('UNVERIFIED_RESOLUTION');
    const payout=D(current.quantity).mul(m.payouts[current.outcome]);
    const payload=JSON.parse(current.payload);const prob=payload.estimated_yes_probability;
    Object.assign(payload,{payout:payout.toFixed(),profit:payout.minus(current.cost).toFixed(),settled_at:now(),resolution_evidence:m.resolution_evidence,brier_score:prob===null?null:D(prob).minus(m.payouts.YES).pow(2).toFixed(),ex_ante_review:'La qualité initiale dépend des sources et probabilités disponibles ; le résultat seul ne valide ni n’invalide la décision.'});
    this.run('INSERT INTO ledger VALUES(?,?,?,?,?)',current.id+':settle',now(),'SETTLEMENT',payout.toFixed(),current.id);
    this.run("UPDATE positions SET status='SETTLED',payload=? WHERE id=?",JSON.stringify(payload),current.id);
    this.event(current.id+':settled','SETTLEMENT',`Pari réglé : ${payout.toFixed()} unités récupérées.`,'SECRETARY',payload.proposal.meeting_id,{position_id:current.id,profit:payload.profit,payout:payload.payout,question:payload.question});
    this.event(current.id+':lesson','LESSON',`Retour factuel sur « ${payload.question} » : résultat net ${payload.profit} unités. Probabilité OUI annoncée : ${prob===null?'inconnue':prob}. Score de Brier : ${payload.brier_score??'non calculable'}. Une issue favorable ne suffit pas à prouver une bonne prévision.`,'SECRETARY',payload.proposal.meeting_id,{category:payload.category,estimated_yes_probability:prob,result:m.payouts,brier_score:payload.brier_score,expected_edge_at_purchase:payload.expected_edge_per_share,ex_ante_review:payload.ex_ante_review});
    return true;
  });}
  notify(id:string,title:string,message:string,url:string,priority=3){this.run("INSERT OR IGNORE INTO notifications VALUES(?,?,'PENDING',0,?,NULL)",id,now(),JSON.stringify({title,message,url,priority}));this.enqueue('notify:'+id,'NOTIFY',{id});}
  cache<T=any>(key:string):T|null{const r=this.one('SELECT payload FROM transient_cache WHERE key=? AND expires_at>?',key,now());return r?JSON.parse(r.payload):null;}
  putCache(key:string,payload:any,seconds=3600){this.run('INSERT INTO transient_cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET expires_at=excluded.expires_at,payload=excluded.payload',key,new Date(Date.now()+seconds*1000).toISOString(),JSON.stringify(payload));}
  prune(){this.run('DELETE FROM transient_cache WHERE expires_at<?',now());/* Financial, document and meeting evidence is never pruned. */}
  export(){const result:Record<string,any>={schema_version:3,exported_at:now()};for(const t of ['meta','documents','markets','dossiers','meetings','proposals','votes','events','ledger','positions','fills','counterfactuals','jobs','calls','notifications'])result[t]=this.rows(`SELECT * FROM ${t}`);return result;}
}
