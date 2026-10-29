import {DurableObject} from 'cloudflare:workers';
import {Repository} from './repository';
import {Engine} from './engine';
import {CONFIG,now,type Env} from './domain';

const json=(v:unknown,status=200)=>Response.json(v,{status,headers:{'Cache-Control':'no-store'}});
async function authorized(r:Request,env:Env){
  if(!env.ADMIN_TOKEN)return false;
  const digest=async(s:string)=>new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)));
  const a=await digest(r.headers.get('authorization')||''),b=await digest('Bearer '+env.ADMIN_TOKEN);
  let diff=0;for(let i=0;i<a.length;i++)diff|=a[i]^b[i];return diff===0;
}
export class Council extends DurableObject<Env>{
  repo:Repository; engine:Engine; private processing=false;
  constructor(ctx:DurableObjectState,env:Env){
    super(ctx,env);this.repo=new Repository(ctx.storage.sql,f=>ctx.storage.transactionSync(f));this.engine=new Engine(this.repo,env);
  }
  async fetch(r:Request){
    const u=new URL(r.url),path=u.pathname;
    this.engine.prepare(r.headers.get('x-board-id')||this.env.EXPERIMENT_ID,r.headers.get('x-board-mode')==='validation'?'validation':'live');
    try{
      if(path==='/api/ws'){
        if(r.headers.get('Upgrade')?.toLowerCase()!=='websocket')return json({error:'WEBSOCKET_REQUIRED'},426);
        const pair=new WebSocketPair();this.ctx.acceptWebSocket(pair[1]);return new Response(null,{status:101,webSocket:pair[0]});
      }
      if(path==='/api/health')return json({state:this.repo.state(),health:this.repo.get('health'),research_collector:this.repo.get('research_collector'),storage_bytes:this.ctx.storage.sql.databaseSize});
      if(path==='/api/state')return json(this.engine.summary());
      if(path==='/api/events')return json({events:this.repo.events(Math.max(0,Number(u.searchParams.get('after'))||0),u.searchParams.get('meeting')||undefined,100)});
      if(path==='/api/meeting')return json({meeting:this.repo.meeting(u.searchParams.get('id')||''),events:this.repo.events(0,u.searchParams.get('id')||'',300)});
      if(path==='/api/document'){
        const d=this.repo.one('SELECT * FROM documents WHERE id=?',u.searchParams.get('id')||'');return d?json(d):json({error:'NOT_FOUND'},404);
      }
      if(path==='/tick'){this.engine.tick();await this.arm();return json({ok:true});}
      if(path==='/admin/preflight'&&r.method==='POST'){
        this.repo.enqueue('preflight:'+now(),'PREFLIGHT',{});await this.arm();return json({queued:true},202);
      }
      if(path==='/admin/start'&&r.method==='POST'){
        const b:any=await r.json();if(b.confirm!==this.repo.state()!.id) return json({error:'EXPLICIT_EXPERIMENT_ID_REQUIRED'},400);
        const s=await this.engine.start();await this.arm();return json(s);
      }
      if(path==='/admin/tick'&&r.method==='POST'){this.engine.tick();await this.arm();return json({ok:true});}
      if(path==='/admin/export')return json(this.repo.export());
      if(path==='/admin/research'&&r.method==='POST'){
        const b:any=await r.json(),url=new URL(b.url),age=Date.now()-Date.parse(b.fetched_at);
        if(!['site.api.espn.com','api.opendota.com'].includes(url.hostname)||url.protocol!=='https:'||url.username||url.password||age< -5000||age>3600000||JSON.stringify(b.data).length>4000000)throw Error('INVALID_RESEARCH_FEED');
        if(url.hostname==='site.api.espn.com'&&!/^\/apis\/site\/v2\/sports\/(basketball|soccer|tennis)\/[a-z0-9.]+\/scoreboard$/.test(url.pathname))throw Error('INVALID_RESEARCH_PATH');
        if(url.hostname==='api.opendota.com'&&url.pathname!=='/api/teams')throw Error('INVALID_RESEARCH_PATH');
        this.repo.putCache('research:'+url.href,{fetched_at:b.fetched_at,data:b.data},Math.max(1,Math.floor((3600000-age)/1000)));
        this.repo.set('research_collector',{at:now(),last_source:url.hostname,last_fetched_at:b.fetched_at});return json({accepted:true});
      }
      if(path==='/admin/notification-outbox')return json({notifications:this.repo.rows("SELECT id,payload FROM notifications WHERE status='PENDING' ORDER BY created_at LIMIT 20").map(n=>({id:n.id,...JSON.parse(n.payload)})),topic:this.env.NTFY_TOPIC});
      if(path==='/admin/notification-ack'&&r.method==='POST'){const b:any=await r.json();if(typeof b.id!=='string')throw Error('INVALID_ID');this.repo.run("UPDATE notifications SET status='SENT',error=NULL WHERE id=?",b.id);return json({ok:true});}
      if(path==='/admin/notifications/test'&&r.method==='POST'){
        if(!this.env.NTFY_TOPIC)return json({error:'NTFY_NOT_CONFIGURED'},409);
        this.repo.notify('notification-test:'+now(),'PROJECT SURVIVAL — test','Test technique : aucune expérience lancée.',this.env.PUBLIC_ORIGIN+'/?phase=3');
        await this.engine.notifications();return json({sent:this.repo.one("SELECT count(*) n FROM notifications WHERE status='SENT'").n,topic:this.env.NTFY_TOPIC});
      }
      if(path==='/admin/restore'&&r.method==='POST'){
        // Restore only into an empty, explicitly named recovery object. Never reset a running fund.
        if(this.repo.state()?.status!=='READY'||this.repo.one('SELECT count(*) n FROM ledger').n)throw Error('RESTORE_REQUIRES_EMPTY_READY_OBJECT');
        const b:any=await r.json();if(b.schema_version!==3||!Array.isArray(b.meta))throw Error('INVALID_BACKUP');
        const allowed=['meta','documents','markets','dossiers','meetings','proposals','votes','events','ledger','positions','fills','counterfactuals','jobs','calls','notifications'];
        for(const t of allowed)if(!Array.isArray(b[t]))throw Error('INCOMPLETE_BACKUP');
        const restored=b.meta.find((v:any)=>v.key==='state');if(!restored||JSON.parse(restored.value).id!==this.repo.state()!.id)throw Error('BACKUP_ID_MISMATCH');
        this.repo.atomic(()=>{for(const t of allowed){for(const row of b[t]){
          const keys=Object.keys(row);if(keys.some(k=>!/^[a-z_]+$/.test(k)))throw Error('INVALID_COLUMN');
          this.repo.run(`INSERT OR REPLACE INTO ${t} (${keys.join(',')}) VALUES (${keys.map(()=>'?').join(',')})`,...keys.map(k=>row[k]));
        }}});await this.arm();return json({restored:true});
      }
      return json({error:'NOT_FOUND'},404);
    }catch(e){return json({error:this.engine.errorCode(e)},400);}
  }
  async arm(){
    const j=this.repo.one("SELECT min(CASE WHEN status='RUNNING' THEN lease_until ELSE due_at END) at FROM jobs WHERE status IN ('PENDING','RUNNING')");
    if(j?.at){const due=Math.max(Date.now()+100,Date.parse(j.at));const old=await this.ctx.storage.getAlarm();if(!old||old>due)await this.ctx.storage.setAlarm(due);}
  }
  async alarm(){
    if(this.processing){await this.ctx.storage.setAlarm(Date.now()+5000);return;}
    this.processing=true;
    const from=this.repo.one('SELECT max(seq) seq FROM events')?.seq||0;
    let job:any=null;
    try{
      this.engine.tick();job=this.repo.claim();
      if(job){
        // The persisted lease and alarm survive isolates, crashes and deploys.
        await this.ctx.storage.setAlarm(Date.parse(job.lease_until)+100);
        if(job.kind==='PREFLIGHT')await this.engine.preflight();else await this.engine.process(job);
        this.repo.complete(job);
        const h=this.repo.get<any>('health')||{successful:0,failed:0};h.successful++;h.last_success=now();this.repo.set('health',h);
      }
    }catch(e){
      const code=this.engine.errorCode(e),h=this.repo.get<any>('health')||{successful:0,failed:0};h.failed++;h.last_failure={at:now(),code,job:job?.kind};this.repo.set('health',h);
      if(job){
        if(job.attempt<3&&job.kind!=='ANALYZE')this.repo.retry(job,code,Math.min(120,15*2**job.attempt));
        else{
          this.repo.run("UPDATE jobs SET status='FAILED',lease_until=NULL,error=? WHERE id=?",code,job.id);
          if(job.kind==='MEETING'){const m=this.repo.meeting(job.payload.id);if(m&&['RUNNING','PAUSED'].includes(m.status))this.engine.endMeeting(m,'CANCELLED','Incident technique : '+code+'. Les fonds restent intacts.');}
        }
        this.repo.event(job.id+':error:'+job.attempt,'INCIDENT','Incident technique : '+code,'SECRETARY',job.payload?.id?.startsWith('meeting:')?job.payload.id:null,{job:job.kind,attempt:job.attempt});
        if(job.kind!=='NOTIFY')this.repo.notify('incident:'+job.id,'Incident technique',code,this.env.PUBLIC_ORIGIN+'/?phase=3',4);
      }
    }finally{
      this.processing=false;
      const events=this.repo.events(from,undefined,100);
      if(events.length)for(const socket of this.ctx.getWebSockets())try{socket.send(JSON.stringify({type:'events',events}));}catch{socket.close(1011,'Reconnect');}
      this.repo.set('quota',{at:now(),storage_bytes:this.ctx.storage.sql.databaseSize,rows_read_last_step:this.repo.reads,rows_written_last_step:this.repo.writes,warning:this.ctx.storage.sql.databaseSize>CONFIG.quotaWarningBytes});
      this.repo.reads=0;this.repo.writes=0;
      await this.ctx.storage.deleteAlarm();await this.arm();
    }
  }
  webSocketMessage(ws:WebSocket,message:string|ArrayBuffer){if(message==='ping')ws.send('pong');}
  webSocketClose(ws:WebSocket,code:number){ws.close(code,'Closed');}
}
export default {
  async fetch(r:Request,env:Env){
    const u=new URL(r.url),admin=u.pathname.startsWith('/admin/');
    if(r.method==='OPTIONS')return new Response(null,{headers:cors(r,env)});
    if(admin&&!await authorized(r,env))return json({error:'UNAUTHORIZED'},401);
    if(!admin&&!u.pathname.startsWith('/api/'))return json({error:'NOT_FOUND'},404);
    const instance=admin?u.searchParams.get('instance'):null;
    if(instance&&!/^(validation|recovery)-[a-zA-Z0-9-]{1,60}$/.test(instance))return json({error:'INVALID_INSTANCE'},400);
    const id=instance||env.EXPERIMENT_ID,headers=new Headers(r.headers);headers.set('x-board-id',id);headers.set('x-board-mode',instance?'validation':'live');
    const stub=env.COUNCIL.get(env.COUNCIL.idFromName(id));const response=await stub.fetch(new Request(r,{headers}));
    if(response.status===101)return response;
    const out=new Response(response.body,response);for(const [k,v]of Object.entries(cors(r,env)))out.headers.set(k,v);return out;
  },
  async scheduled(_c:ScheduledController,env:Env,ctx:ExecutionContext){ctx.waitUntil(env.COUNCIL.get(env.COUNCIL.idFromName(env.EXPERIMENT_ID)).fetch(new Request('https://internal/tick',{headers:{'x-board-id':env.EXPERIMENT_ID}})));},
} satisfies ExportedHandler<Env>;
function cors(r:Request,env:Env):Record<string,string>{const origin=r.headers.get('Origin');return origin&&(origin===env.PUBLIC_ORIGIN||/^http:\/\/(localhost|127\.0\.0\.1):5173$/.test(origin))?{'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Methods':'GET,OPTIONS','Vary':'Origin'}:{};}
