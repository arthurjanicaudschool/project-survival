import {z} from 'zod';
import {CONFIG,CATEGORIES,MEMBERS,AnalysisSchema,SpeechSchema,ChairSchema,VoteSchema,ArbitrationSchema,panel,now,reasonLabel,type Env,type State,type Category,type MemberId,type Proposal,type Market,type Source,type Vote} from './domain';
import {Repository} from './repository';
import {Markets,normalize,hash,coveragePreference} from './markets';
import {Azure,ProviderError,usageCost} from './azure';
import {D,execute,tally,arbitrate} from './finance';
import {nextSlots,parisDay} from './schedule';

type MarketService=Pick<Markets,'catalog'|'inspect'|'evidence'|'fx'>&{synthetic?:boolean};
type AgentService=Pick<Azure,'ask'>&{synthetic?:boolean};
export class Engine {
  constructor(public repo:Repository,public env:Env,public markets:MarketService=new Markets(repo),public azure:AgentService=new Azure(repo,env)){}
  prepare(id=this.env.EXPERIMENT_ID,mode:State['mode']='live'){
    if((this.markets.synthetic||this.azure.synthetic)&&mode!=='demo')throw Error('SYNTHETIC_DATA_FORBIDDEN');
    const old=this.repo.state();if(old){if(old.id!==id)throw Error('EXPERIMENT_ID_MISMATCH');return old;}
    const s:State={id,mode,status:'READY',started_at:null,end_at:null,betting_deadline:null,fx:null,initial_eur:CONFIG.initialEur,created_at:now(),updated_at:now(),last_scan:null,last_cycle:null,emergency_day:'',emergency_count:0,last_emergency:null,last_error:null};
    this.repo.save(s);this.repo.set('policy',CONFIG);return s;
  }
  async start(){
    const s=this.repo.state()!;if(s.status!=='READY')throw Error('START_IS_NEVER_A_RESET');
    const fx=await this.markets.fx();
    if(s.mode!=='demo'){
      const pf=this.repo.get<any>('preflight');
      if(!pf?.azure_ok||!pf?.all_categories_ready||Date.now()-Date.parse(pf.at)>86400000)throw Error('RECENT_FIVE_CATEGORY_PREFLIGHT_REQUIRED');
    }
    this.repo.atomic(()=>{
      if(this.repo.state()!.status!=='READY')throw Error('START_IS_NEVER_A_RESET');
      s.started_at=now();s.end_at=new Date(Date.now()+CONFIG.durationHours*3600000).toISOString();s.betting_deadline=new Date(Date.parse(s.end_at)-CONFIG.settlementBufferHours*3600000).toISOString();s.fx=fx;s.status='RUNNING';
      this.repo.run('INSERT INTO ledger VALUES(?,?,?,?,?)',s.id+':initial',now(),'INITIAL',D(s.initial_eur).mul(fx.usd_per_eur).toFixed(),s.id);
      this.repo.save(s);this.repo.event(s.id+':start','START','Le défi de sept jours commence. Fonds commun : 1 000 € fictifs.');
      for(const slot of nextSlots(s.started_at,s.end_at,40))this.repo.enqueue('slot:'+slot,'SLOT',{slot},slot);
      this.tick();
    });return s;
  }
  tick(){
    const s=this.repo.state();if(!s||s.status==='READY'||s.status==='FINISHED')return;
    const at=now(),bucket=Math.floor(Date.now()/(CONFIG.scanMinutes*60000));
    if(Date.now()<Date.parse(s.betting_deadline!))for(const category of CATEGORIES)this.repo.enqueue(`scan:${bucket}:${category}`,'SCAN',{category});
    this.repo.enqueue('settle:'+bucket,'SETTLE',{});
    if(Date.now()>=Date.parse(s.end_at!))this.repo.enqueue('finish:'+bucket,'FINISH',{});
    this.repo.prune();
  }
  async preflight(){
    const at=now();
    const r:any={at,azure_ok:false,market_ok:false,categories:{},notifications_configured:!!this.env.NTFY_TOPIC,mode:'technical_validation_no_start'};
    try{await this.azure.ask('preflight:'+at,'CHAIR','connectivity_check',{instruction:'Vérification technique uniquement. Répondre ok true. Aucun débat ni investissement.'},z.object({ok:z.boolean()}).strict());r.azure_ok=true;}catch(e){r.azure_error=this.errorCode(e);}
    this.repo.set('preflight',r);
    for(const category of CATEGORIES)this.repo.enqueue(`preflight:${at}:${category}`,'PREFLIGHT_CATEGORY',{category});
    return r;
  }
  async preflightCategory(category:Category){
    const r=this.repo.get<any>('preflight'),deadline=new Date(Date.now()+(168-6)*3600000).toISOString();
    if(!r)return;
      try{
        const candidates=await this.markets.catalog(category,deadline);let checked=0,usable=0,sourceCount=0;const failures:string[]=[];
        const admissible=candidates.filter(raw=>{try{const m=normalize(raw,category);return m.active&&m.start_at&&Date.parse(m.start_at)>Date.now()&&Date.parse(m.event_end_at)<=Date.parse(deadline);}catch{return false;}}).sort((a,b)=>coveragePreference(normalize(b,category))-coveragePreference(normalize(a,category)));
        const seenGroups=new Set();const diverse=admissible.filter(raw=>{const group=String(raw.events?.[0]?.id||raw.id);if(seenGroups.has(group))return false;seenGroups.add(group);return true;});
        for(const raw of diverse.slice(0,3)){
          try{this.repo.putMarket(normalize(raw,category));const m=await this.markets.inspect(String(raw.id));checked++;const sources=await this.markets.evidence(m);const independent=sources.filter(s=>s.status==='VERIFIED'&&s.provider!=='Polymarket');if(independent.length){usable++;sourceCount+=independent.length;}this.repo.putMarket(m);for(const source of sources)if(source.status==='VERIFIED')this.repo.document(source);}catch(e){failures.push(this.errorCode(e));}
          if(usable)break;
        }
        r.categories[category]={discovered:candidates.length,admissible:admissible.length,checked,usable,independent_sources:sourceCount,errors:failures};
      }catch(e){r.categories[category]={discovered:0,usable:0,error:this.errorCode(e)};}
    r.market_ok=Object.values(r.categories).some((c:any)=>c.usable>0);r.all_categories_ready=CATEGORIES.every(c=>r.categories[c]?.usable>0);r.completed_categories=Object.keys(r.categories).length;
    this.repo.set('preflight',r);return r;
  }
  async process(job:any){
    if(job.kind==='SCAN')await this.scan(job.payload.category);
    else if(job.kind==='PREFLIGHT_CATEGORY')await this.preflightCategory(job.payload.category);
    else if(job.kind==='NOTIFY')await this.notifications(job.payload.id);
    else if(job.kind==='ANALYZE')await this.analyze(job.payload.id);
    else if(job.kind==='SLOT')await this.slot(job.payload.slot,'ORDINARY');
    else if(job.kind==='EMERGENCY')await this.slot(job.payload.slot,'EXTRAORDINARY',job.payload.id);
    else if(job.kind==='MEETING')await this.advance(job.payload.id);
    else if(job.kind==='SETTLE')await this.settlements();
    else if(job.kind==='FINISH')this.finish();
    else throw Error('UNKNOWN_JOB');
  }
  async scan(category:Category){
    const s=this.repo.state()!;if(s.status!=='RUNNING'||Date.now()>=Date.parse(s.betting_deadline!))return;
    const raw=await this.markets.catalog(category,s.betting_deadline!);const candidates:any[]=[];const exclusions:Record<string,number>={};
    for(const r of raw){
      try{
        const m=normalize(r,category);
        if(!m.active||!m.description||!m.resolution_source)throw Error('MISSING_RULES_OR_CLOSED');
        if(!m.start_at||Date.parse(m.start_at)<=Date.now())throw Error('EVENT_ALREADY_STARTED');
        if(Date.parse(m.event_end_at)>Date.parse(s.betting_deadline!))throw Error('OUTSIDE_WINDOW');
        if(this.repo.one('SELECT id FROM positions WHERE market_id=?',m.id))continue;
        const previous=this.repo.dossier(m.id);if(previous&&['INVESTED','IN_MEETING'].includes(previous.status))continue;
        const hours=(Date.parse(m.start_at)-Date.now())/3600000;
        const priority=Math.log10(Math.max(1,Number(m.liquidity)))*10+Math.max(0,20-hours)+(previous?-8:10)+coveragePreference(m);
        candidates.push({m,priority,previous});
      }catch(e){const c=this.errorCode(e);exclusions[c]=(exclusions[c]||0)+1;}
    }
    candidates.sort((a,b)=>b.priority-a.priority);
    let prepared=0;const failures:string[]=[];
    const groups=new Set();const diversified=candidates.filter(c=>{if(groups.has(c.m.group))return false;groups.add(c.m.group);return true;});
    for(const {m,priority,previous} of diversified.slice(0,3)){
      try{
        // Review on meaningful change or after cooldown; never run an AI for
        // every changed order-book hash or mere collector timestamp.
        this.repo.putMarket(m);const full=await this.markets.inspect(m.id);this.repo.putMarket(full);
        const price=full.books.YES?.asks[0]?.price;
        const oldPrice=previous?.payload?.reference_price;
        const aged=!previous||Date.now()-Date.parse(previous.payload.analyzed_at||previous.updated_at)>=CONFIG.analysisCooldownMinutes*60000;
        const changed=oldPrice&&price&&Math.abs(Number(price)-Number(oldPrice))>=.04;
        if(previous&&!aged&&!changed)continue;
        const sources=await this.markets.evidence(full);const fingerprint=await hash({question:full.question,rules:full.description,end:full.event_end_at,price,sources:sources.filter(x=>x.status==='VERIFIED').map(x=>x.id)});
        if(previous?.hash===fingerprint&&!aged)continue;
        const revision=fingerprint+':'+Math.floor(Date.now()/(CONFIG.analysisCooldownMinutes*60000));
        this.repo.putDossier({id:full.id,market_id:full.id,category,status:'PENDING',priority,hash:revision,payload:{source_ids:sources.filter(x=>x.status==='VERIFIED').map(x=>x.id),source_failures:sources.filter(x=>x.status!=='VERIFIED').map(x=>x.provider),reference_price:price,previous_analysis:previous?.payload?.analysis||null,analyzed_at:previous?.payload?.analyzed_at||null}});
        this.repo.enqueue('analysis:'+full.id+':'+revision,'ANALYZE',{id:full.id});prepared++;
      }catch(e){failures.push(this.errorCode(e));}
    }
    this.repo.set('scan:'+category,{at:now(),discovered:raw.length,eligible:candidates.length,prepared,exclusions,errors:failures});
    s.last_scan=now();this.repo.save(s);
    this.repo.event(`scan:${category}:${Math.floor(Date.now()/600000)}`,'SCAN',`${category} : ${raw.length} marchés détectés, ${candidates.length} admissibles, ${prepared} dossiers actualisés.`,'SECRETARY',null,{category,exclusions,errors:failures});
  }
  sources(ids:string[]):Source[]{return ids.map(id=>this.repo.one('SELECT * FROM documents WHERE id=?',id)).filter(Boolean);}
  context(d:any,meeting?:any,p?:Proposal){
    const s=this.repo.state()!,m=this.repo.market(d.market_id);
    const memory=this.repo.rows("SELECT kind,text,details FROM events WHERE kind IN ('SETTLEMENT','LESSON') ORDER BY seq DESC LIMIT 5").map(e=>({kind:e.kind,text:e.text,details:JSON.parse(e.details)}));
    const positions=this.repo.rows('SELECT market_id,outcome,status,cost,quantity,payload FROM positions').map(r=>({...r,payload:JSON.parse(r.payload)}));
    const books=Object.fromEntries(Object.entries(m.books||{}).map(([k,b]:any)=>[k,{observed_at:b.observed_at,asks:b.asks.slice(0,5),minimum:b.minimum,tick:b.tick,fee_rate:b.fee_rate,fee_exponent:b.fee_exponent}]));
    return {now:now(),market:{...m,books:undefined},executable_books:books,proposal:p||null,fx:s.fx,cash:this.repo.cash(),fund_initial_eur:s.initial_eur,betting_deadline:s.betting_deadline,mode:s.mode,
      sources:this.sources(d.payload.source_ids||[]),memory,positions,previous_analysis:d.payload.previous_analysis||null,
      history:meeting?this.repo.events(0,meeting.id,200).filter(e=>['SPEECH','AMENDMENT','QUESTION'].includes(e.kind)).slice(-10):[],
      voting_rules:{votes_required:4,majority:3,abstention_requires:'essential blocker and reconsideration condition; disagreement means AGAINST',chair_can_change_mind_in_tie:true,technical_veto_only:true}};
  }
  citations(value:any,sources:Source[]){
    const clean=(s:string)=>s.replace(/\s+/g,' ').trim().toLowerCase();
    for(const c of value.citations||[]){const source=sources.find(s=>s.id===c.source_id&&s.status==='VERIFIED');if(!source||!clean(source.text).includes(clean(c.quote)))throw Error('UNVERIFIED_CITATION');}
  }
  async ask<T>(id:string,actor:MemberId,phase:string,context:any,schema:z.ZodType<T>,meeting:string|null=null):Promise<T>{
    if(meeting)this.repo.event(id+':thinking','THINKING',`${MEMBERS.find(m=>m.id===actor)?.name} prépare son intervention.`,actor,meeting);
    let value:any=await this.azure.ask(id,actor,phase,context,schema,meeting);
    if(value.document_requests?.length){
      const found:Source[]=[];
      for(const query of value.document_requests){const documents=this.repo.retrieve(query);found.push(...documents);this.repo.event(id+':document:'+await hash(query),'DOCUMENT',documents.length?`Le secrétaire retrouve ${documents.length} document(s) pour « ${query} ».`:`Le secrétaire ne trouve pas de document pertinent pour « ${query} ».`, 'SECRETARY',meeting,{query,documents:documents.map(d=>({id:d.id,title:d.title,url:d.url}))});}
      value=await this.azure.ask(id+':documents',actor,phase,{...context,secretary_results:found.map(d=>({...d,text:d.text.slice(0,1800)})),instruction:'Voici les résultats de ta demande. Termine ta réponse sans nouvelle demande documentaire.'},schema,meeting);
      this.citations(value,[...(context.sources||[]),...found]);
    }else this.citations(value,context.sources||[]);
    return value;
  }
  async analyze(id:string){
    const s=this.repo.state()!,d=this.repo.dossier(id);if(!d||s.status!=='RUNNING'||Date.now()>=Date.parse(s.betting_deadline!))return;
    if(d.status!=='PENDING')return;
    const actor=d.category.toUpperCase() as MemberId;
    try{
      const analysis=await this.ask(`analysis:${d.id}:${d.hash}`,actor,'independent_analysis',this.context(d),AnalysisSchema);
      if(analysis.recommendation==='PROPOSE'&&(!analysis.side||!analysis.amount||!analysis.max_price||analysis.estimated_yes_probability===null))throw Error('INCOMPLETE_INVESTMENT_PROPOSAL');
      d.payload.analysis=analysis;d.payload.analyzed_at=now();d.status=analysis.recommendation==='PROPOSE'?'PROPOSED':'WAIT';this.repo.putDossier(d);
      this.repo.event(`analysis:${d.id}:${d.hash}:speech`,'ANALYSIS',analysis.speech,actor,null,{market_id:d.market_id,recommendation:analysis.recommendation,estimated_yes_probability:analysis.estimated_yes_probability});
      if(analysis.lesson)this.repo.event(`analysis:${d.id}:${d.hash}:lesson`,'LESSON',analysis.lesson,actor,null,{market_id:d.market_id});
      if(analysis.recommendation==='WAIT')this.counterfactual(d,null,'WAIT',analysis.reasoning,analysis.side||'YES');
      else if(analysis.urgent)this.emergency(d,analysis.urgency_reason);
    }catch(e){d.status='TECHNICAL_ERROR';d.payload.error=this.errorCode(e);d.payload.analyzed_at=now();this.repo.putDossier(d);throw e;}
  }
  emergency(d:any,reason:string){
    const s=this.repo.state()!,m=this.repo.market(d.market_id);const next=nextSlots(now(),s.end_at,1)[0];
    const urgent=m.start_at&&(!next||Date.parse(m.start_at)<Date.parse(next)+1800000);
    const day=parisDay(now());if(s.emergency_day!==day){s.emergency_day=day;s.emergency_count=0;}
    if(!urgent||d.priority<30||s.emergency_count>=CONFIG.emergencyMaxPerDay||s.last_emergency&&Date.now()-Date.parse(s.last_emergency)<CONFIG.emergencyCooldownMinutes*60000)return;
    if(this.repo.one("SELECT id FROM meetings WHERE status IN ('RUNNING','PAUSED')"))return;
    s.emergency_count++;s.last_emergency=now();this.repo.save(s);
    const slot='urgent:'+d.id+':'+d.hash.slice(0,16);this.repo.enqueue(slot,'EMERGENCY',{id:d.id,slot});
    this.repo.event(slot+':request','EMERGENCY_REQUEST',reason,d.category.toUpperCase(),null,{market_id:d.market_id,priority:d.priority});
  }
  async slot(slot:string,kind:string,onlyId?:string){
    const s=this.repo.state()!;if(s.status!=='RUNNING')return;
    const id='meeting:'+slot;if(this.repo.meeting(id))return;
    if(this.repo.one("SELECT id FROM meetings WHERE status IN ('RUNNING','PAUSED')")){
      if(kind==='ORDINARY'&&Date.now()-Date.parse(slot)<300000)throw new ProviderError('MEETING_BUSY');
      this.repo.event(id+':missed','SLOT_MISSED','Créneau reporté : une réunion précédente est encore active.','SECRETARY',null,{slot,kind});return;
    }
    const list=(onlyId?[this.repo.dossier(onlyId)]:this.repo.rows("SELECT * FROM dossiers WHERE status='PROPOSED' ORDER BY priority DESC").map(r=>({...r,payload:JSON.parse(r.payload)}))).filter(Boolean);
    const agenda:any[]=[];const used=new Set();
    for(const d of list){const m=this.repo.market(d.market_id);if(!m?.active||Date.parse(m.start_at)<=Date.now()||Date.parse(m.event_end_at)>Date.parse(s.betting_deadline!))continue;if(used.has(d.category)&&list.some(x=>!used.has(x.category)))continue;agenda.push(d);used.add(d.category);if(agenda.length>=CONFIG.maxAgenda)break;}
    if(!agenda.length){
      const reasons=this.repo.rows('SELECT category,status,count(*) AS count FROM dossiers GROUP BY category,status');
      const late=Date.now()>=Date.parse(s.betting_deadline!);
      this.repo.putMeeting({id,slot,kind,status:'NO_AGENDA',stage:'DONE',created_at:now(),started_at:null,finished_at:now(),payload:{reasons,summary:late?'La fenêtre de nouveaux paris est fermée. Le suivi des règlements continue.':'Aucune proposition exploitable disponible. Les attentes et erreurs restent distinctes ; les recherches continuent.',next_research:CATEGORIES}});
      this.repo.event(id+':bulletin','BULLETIN',late?'Fin de la fenêtre de prise de paris ; suivi des résultats uniquement.':'Bilan automatique du créneau : aucune proposition exploitable. Consulter les dossiers pour distinguer attentes et erreurs.','SECRETARY',id,{reasons});
      return;
    }
    const m={id,slot,kind,status:'RUNNING',stage:'DISCUSS',created_at:now(),started_at:now(),finished_at:null,payload:{agenda:agenda.map(d=>d.id),index:0,deadline:new Date(Date.now()+CONFIG.maxMeetingSeconds*1000).toISOString(),unavailable:{},retried:false,abstention_reviewed:false}};
    this.repo.putMeeting(m);
    for(const d of agenda){d.status='IN_MEETING';this.repo.putDossier(d);}
    this.repo.event(id+':start','MEETING_START',`Le conseil examine ${agenda.length} dossier(s). Les analyses initiales ont été réalisées séparément.`,'SECRETARY',id,{kind,agenda:agenda.map(d=>({id:d.id,category:d.category,question:this.repo.market(d.market_id).question})),late_seconds:kind==='ORDINARY'?Math.max(0,(Date.now()-Date.parse(slot))/1000):0});
    this.repo.notify(id+':start',kind==='ORDINARY'?'Le conseil commence':'Conseil extraordinaire',`${agenda.length} dossier(s) à examiner.`,this.link(id));
    this.enqueueMeeting(m);
  }
  enqueueMeeting(m:any,delay=0){this.repo.enqueue(`${m.id}:${m.payload.index}:${m.stage}:${m.payload.retried?'retry':''}:${m.payload.abstention_reviewed?'review':''}`,'MEETING',{id:m.id},new Date(Date.now()+delay).toISOString());}
  speech(id:string,meeting:any,actor:MemberId,value:any){this.repo.event(id,'SPEECH',value.speech,actor,meeting.id,{estimated_yes_probability:value.estimated_yes_probability??null,objection:value.objection||null,citations:value.citations||[]});}
  async advance(id:string){
    const meeting=this.repo.meeting(id);if(!meeting||!['RUNNING','PAUSED'].includes(meeting.status))return;
    const s=this.repo.state()!,d=this.repo.dossier(meeting.payload.agenda[meeting.payload.index]);
    if(Date.now()>Date.parse(meeting.payload.deadline)||Date.now()>=Date.parse(s.betting_deadline!)){this.endMeeting(meeting,'CANCELLED','Réunion interrompue : délai atteint. Aucun nouveau vote ou achat ne sera inventé.');return;}
    const market=this.repo.market(d.market_id);let p=this.repo.proposal(meeting.id+':'+d.id);
    if(!p){const a=d.payload.analysis; p={id:meeting.id+':'+d.id,meeting_id:meeting.id,market_id:d.market_id,version:1,side:a.side,amount:a.amount,max_price:a.max_price,status:'DISCUSSING',reason:a.reasoning,created_at:now()};this.repo.putProposal(p);this.repo.event(p.id+':initial','SPEECH',a.speech,d.category.toUpperCase(),meeting.id,{proposal:p,independent_analysis:true});}
    const context=this.context(d,meeting,p),key=`${p.id}:v${p.version}`;
    if(meeting.stage==='DISCUSS'){
      const results=await Promise.allSettled((['QUANT','RISK','CONTRA'] as MemberId[]).map(async actor=>{
        const value=await this.ask(key+':discuss:'+actor,actor,'discussion',context,SpeechSchema,meeting.id);this.speech(key+':speech:'+actor,meeting,actor,value);return {actor,value};
      }));
      meeting.payload.discussion=[];meeting.payload.unavailable={};
      results.forEach((r,i)=>{const actor=['QUANT','RISK','CONTRA'][i];if(r.status==='fulfilled')meeting.payload.discussion.push(r.value);else meeting.payload.unavailable[actor]=this.errorCode(r.reason);});
      meeting.stage='CHAIR';
    }else if(meeting.stage==='CHAIR'){
      const value=await this.ask(key+':chair','CHAIR','chair_question_and_amendment',{...context,discussion:meeting.payload.discussion,instruction:'Pose une question contradictoire utile à un membre. Propose un amendement seulement s’il améliore le dossier ; ce n’est pas une décision d’achat.'},ChairSchema,meeting.id);
      this.speech(key+':chair:speech',meeting,'CHAIR',value);
      if(value.amendment)p=this.amend(meeting,d,p,value.amendment,'CHAIR');
      if(value.question&&panel(d.category).includes(value.question_to as MemberId)){
        meeting.payload.question=value.question;meeting.payload.question_to=value.question_to;
        this.repo.event(key+':question','QUESTION',value.question,'CHAIR',meeting.id,{to:value.question_to});meeting.stage='REBUT';
      }else meeting.stage='VOTE';
    }else if(meeting.stage==='REBUT'){
      const actor=meeting.payload.question_to as MemberId;
      try{
        const value=await this.ask(key+':rebut',actor,'answer_objection',{...context,question:meeting.payload.question,instruction:'Réponds directement à la question. Tu peux défendre ou modifier ta position ; aucune répétition de prudence générique.'},SpeechSchema,meeting.id);
        this.speech(key+':rebut:speech',meeting,actor,value);if(value.amendment)p=this.amend(meeting,d,p,value.amendment,actor);
      }catch(e){meeting.payload.unavailable[actor]=this.errorCode(e);}
      meeting.stage='VOTE';
    }else if(meeting.stage==='VOTE'||meeting.stage==='VOTE_RETRY'||meeting.stage==='ABSTENTION'){
      const expected=panel(d.category),review=meeting.stage==='ABSTENTION',retry=meeting.stage==='VOTE_RETRY';
      const existing=this.readVotes(p);
      const actors=review?existing.filter(v=>v.vote==='ABSTAIN').map(v=>v.member_id):retry?expected.filter(a=>!existing.some(v=>v.member_id===a)):expected;
      const round=review?2:1;
      await Promise.allSettled(actors.map(async actor=>{
        try{
          const value=await this.ask(key+`:vote:${round}:${retry?'retry:':''}`+actor,actor,review?'abstention_reconsideration':'independent_vote',{
            ...context,proposal:p,instruction:review?'Précise le blocage, consulte les documents utiles et décide si tu peux voter POUR ou CONTRE. Tu peux maintenir une abstention réfléchie ; aucun vote forcé.':'Vote personnellement sur cette proposition exacte. Les autres votes ne te sont pas montrés. Accepte une incertitude argumentée ; justifie le montant.'},VoteSchema,meeting.id);
          if(value.proposal_id!==p!.id||value.proposal_version!==p!.version)throw Error('VOTE_WRONG_PROPOSAL');
          if(value.vote==='ABSTAIN'&&(value.abstention_reason.trim().length<25||value.reconsider_if.trim().length<15))throw Error('UNJUSTIFIED_ABSTENTION');
          this.repo.run('INSERT OR IGNORE INTO votes VALUES(?,?,?,?,?)',p!.id,p!.version,round,actor,JSON.stringify({...value,member_id:actor}));delete meeting.payload.unavailable[actor];
        }catch(e){meeting.payload.unavailable[actor]=this.errorCode(e);}
      }));
      const votes=this.readVotes(p),missing=expected.filter(a=>!votes.some(v=>v.member_id===a));
      if(missing.length&&!meeting.payload.retried&&Date.now()+90000<Date.parse(meeting.payload.deadline)){
        meeting.payload.retried=true;meeting.stage='VOTE_RETRY';meeting.status='PAUSED';
        this.repo.event(key+':paused','INCIDENT','La réunion est suspendue pour tenter de rétablir la disponibilité des membres.','SECRETARY',meeting.id,{missing});
        this.repo.notify(key+':paused','Conseil suspendu',`${missing.length} membre(s) temporairement indisponible(s).`,this.link(meeting.id),4);
        this.repo.putMeeting(meeting);this.enqueueMeeting(meeting,15000);return;
      }
      meeting.status='RUNNING';
      const result=tally(expected,votes,p,review||meeting.payload.abstention_reviewed);
      this.repo.event(key+':votes:'+round+':'+(retry?'retry':'first'),'VOTES','Les votes indépendants sont révélés.','SECRETARY',meeting.id,{proposal:p,votes,tally:result,unavailable:meeting.payload.unavailable});
      if(result.decision==='REVIEW_ABSTENTION'){meeting.stage='ABSTENTION';meeting.payload.abstention_reviewed=true;}
      else if(result.decision==='TIE'){meeting.stage='ARBITRATE';meeting.payload.tally=result;}
      else if(result.decision==='APPROVE'){p.status='APPROVED';this.repo.putProposal(p);meeting.stage='EXECUTE';}
      else {this.reject(meeting,d,p,result.decision,result.reason);return;}
    }else if(meeting.stage==='ARBITRATE'){
      const value=await this.ask(key+':arbitration','CHAIR','tie_arbitration',{...context,proposal:p,votes:this.readVotes(p),instruction:'Égalité persistante après réinterrogation des abstinents. Prends du recul. Tu peux APPROVE, REJECT ou CANCEL, même si cela contredit ton premier vote. Explique pourquoi.'},ArbitrationSchema,meeting.id);
      if(value.proposal_id!==p.id||value.proposal_version!==p.version)throw Error('ARBITRATION_WRONG_PROPOSAL');
      const decision=arbitrate(meeting.payload.tally,value.decision,true);this.speech(key+':arbitration:speech',meeting,'CHAIR',value);
      this.repo.event(key+':arbitration','ARBITRATION',value.speech,'CHAIR',meeting.id,{decision,proposal:p});
      if(decision==='APPROVE'){p.status='APPROVED_BY_ARBITRATION';this.repo.putProposal(p);meeting.stage='EXECUTE';}else {this.reject(meeting,d,p,decision,value.speech);return;}
    }else if(meeting.stage==='EXECUTE'){
      const positionId=`${p.id}:v${p.version}`;
      if(this.repo.one('SELECT id FROM positions WHERE id=?',positionId)){d.status='INVESTED';this.repo.putDossier(d);this.nextDossier(meeting);return;}
      // Read-only public endpoints only. Delay markets are observed again after
      // their matching delay; no live-order API or wallet is used anywhere.
      let fresh=await this.markets.inspect(p.market_id);
      if(fresh.delay_seconds>0){if(fresh.delay_seconds>30)throw Error('UNSUPPORTED_MATCH_DELAY');await new Promise(r=>setTimeout(r,fresh.delay_seconds*1000));fresh=await this.markets.inspect(p.market_id);}
      this.repo.putMarket(fresh);
      const error=this.repo.one('SELECT id FROM positions WHERE market_id=?',fresh.id)?'ALREADY_INVESTED':null;
      const {technicalCheck}=await import('./finance');
      const technical=error||technicalCheck(p,fresh,this.repo.cash(),s.betting_deadline!,now());
      if(technical){this.repo.event(key+':technical','TECHNICAL_REJECTION',reasonLabel(technical),'SECRETARY',meeting.id,{code:technical,proposal:p});this.reject(meeting,d,p,'TECHNICAL_REJECTION',reasonLabel(technical));return;}
      const book=fresh.books[p.side]!;
      const execution=execute(book,p.amount,p.max_price,now(),this.repo.consumed(book.asset_id,book.evidence));
      if(!execution.fills.length){this.reject(meeting,d,p,'TECHNICAL_REJECTION',reasonLabel(execution.reason));return;}
      this.repo.buy(p,fresh,execution,p.reason);p.status='INVESTED';this.repo.putProposal(p);d.status='INVESTED';this.repo.putDossier(d);
      this.nextDossier(meeting);return;
    }
    this.repo.putMeeting(meeting);this.enqueueMeeting(meeting);
  }
  amend(meeting:any,d:any,p:Proposal,a:any,actor:MemberId){
    if(a.market_id!==p.market_id){
      this.repo.event(p.id+':new-market','AMENDMENT_DEFERRED','Changer de marché exige un nouveau dossier et une analyse indépendante du bon spécialiste.',actor,meeting.id,{requested_market_id:a.market_id});return p;
    }
    if(D(a.amount).lte(0)||D(a.max_price).lte(0)||D(a.max_price).gte(1))throw Error('INVALID_AMENDMENT');
    if(a.side===p.side&&D(a.amount).eq(p.amount)&&D(a.max_price).eq(p.max_price))return p;
    p.status='SUPERSEDED';this.repo.putProposal(p);
    const updated={...p,version:p.version+1,side:a.side,amount:a.amount,max_price:a.max_price,status:'DISCUSSING',reason:a.reason,created_at:now()};this.repo.putProposal(updated);
    this.repo.event(updated.id+':amend:'+updated.version,'AMENDMENT',a.reason,actor,meeting.id,{before:p,after:updated,votes_invalidated:true});
    return updated;
  }
  readVotes(p:Proposal):Vote[]{const all=this.repo.rows('SELECT * FROM votes WHERE proposal_id=? AND version=? ORDER BY round DESC',p.id,p.version),seen=new Set();return all.filter(r=>{if(seen.has(r.member_id))return false;seen.add(r.member_id);return true;}).map(r=>JSON.parse(r.payload));}
  reject(meeting:any,d:any,p:Proposal,status:string,reason:string){p.status=status;this.repo.putProposal(p);d.status=status==='REJECT'?'REJECTED':status;d.payload.last_decision=reason;this.repo.putDossier(d);this.counterfactual(d,p,status,reason,p.side);this.repo.event(`${p.id}:v${p.version}:decision`,'DECISION',reason,'SECRETARY',meeting.id,{status,proposal:p});this.nextDossier(meeting);}
  counterfactual(d:any,p:Proposal|null,status:string,reason:string,side:'YES'|'NO'){
    const s=this.repo.state()!,m=this.repo.market(d.market_id);if(!s.fx||!m.books[side])return;
    const id=p?`${p.id}:v${p.version}`:`wait:${d.id}:${d.hash}`;const book=m.books[side];
    const reference=D(10).mul(s.fx.usd_per_eur).toFixed();const ex=execute(book,reference,'0.999999',now());const proof=this.repo.proof(book);
    const payload={market_id:m.id,question:m.question,url:m.url,category:m.category,side,decision:status,reason,reference_eur:'10',reference_quote:reference,observed_at:book.observed_at,
      execution:ex,book_proof:proof,side_basis:p||d.payload.analysis?.side?'Côté proposé par l’agent':'Référence OUI uniquement ; aucune recommandation de l’agent',estimated_yes_probability:d.payload.analysis?.estimated_yes_probability??null,quality_assessment:'Non évaluée ; résultat et pertinence initiale restent séparés.',official_result:null};
    this.repo.run('INSERT OR IGNORE INTO counterfactuals VALUES(?,?,?,?)',id,m.id,ex.fills.length?'PENDING':'NON_EXECUTABLE',JSON.stringify(payload));
  }
  nextDossier(m:any){
    m.payload.index++;m.payload.unavailable={};m.payload.retried=false;m.payload.abstention_reviewed=false;
    if(m.payload.index>=m.payload.agenda.length){this.endMeeting(m,'COMPLETED','Les dossiers prévus ont été examinés. Les votes et décisions sont archivés.');return;}
    m.stage='DISCUSS';this.repo.putMeeting(m);this.enqueueMeeting(m);
  }
  endMeeting(m:any,status:string,summary:string){
    m.status=status;m.stage='DONE';m.finished_at=now();m.payload.summary=summary;this.repo.putMeeting(m);
    // Unexamined agenda entries return to the queue after an interrupted meeting.
    for(const id of m.payload.agenda){const d=this.repo.dossier(id);if(d?.status==='IN_MEETING'){d.status='PROPOSED';this.repo.putDossier(d);}}
    this.repo.event(m.id+':end','MEETING_END',summary,'SECRETARY',m.id,{status});
    this.repo.notify(m.id+':end',status==='COMPLETED'?'Conseil terminé':'Incident au conseil',summary,this.link(m.id),status==='COMPLETED'?3:4);
  }
  async settlements(){
    const ids=new Set<string>([...this.repo.rows("SELECT market_id FROM positions WHERE status='PENDING'"),...this.repo.rows("SELECT market_id FROM counterfactuals WHERE status='PENDING'")].map(r=>r.market_id));
    const backlog=[...ids],cursor=this.repo.get<number>('settlement_cursor')||0;
    for(const id of backlog.slice(cursor,cursor+10)){
      try{
        const m=await this.markets.inspect(id,false);this.repo.putMarket(m);
        if(!m.resolved||!m.payouts)continue;
        for(const position of this.repo.rows("SELECT * FROM positions WHERE market_id=? AND status='PENDING'",id))this.repo.settle(position,m);
        for(const row of this.repo.rows("SELECT * FROM counterfactuals WHERE market_id=? AND status='PENDING'",id)){
          const c=JSON.parse(row.payload),payout=D(c.execution.quantity).mul(m.payouts[c.side as 'YES'|'NO']);
          c.official_result=m.payouts;c.payout=payout.toFixed();c.profit=payout.minus(c.execution.spent).toFixed();c.settled_at=now();c.resolution_evidence=m.resolution_evidence;
          c.brier_score=c.estimated_yes_probability===null?null:D(c.estimated_yes_probability).minus(m.payouts.YES).pow(2).toFixed();
          c.quality_assessment='Résultat théorique connu. Pertinence initiale à examiner selon les sources, l’incertitude et les raisons archivées ; aucun jugement fondé seulement sur le gain.';
          this.repo.run("UPDATE counterfactuals SET status='SETTLED',payload=? WHERE id=?",JSON.stringify(c),row.id);
          this.repo.event(row.id+':review','LESSON',`Occasion non retenue : « ${c.question} ». Une mise théorique de 10 € aurait produit ${D(c.profit).div(this.repo.state()!.fx!.usd_per_eur).toDecimalPlaces(2)} € nets. Motif initial conservé : ${c.reason}. Ce résultat ne suffit pas à qualifier le refus d’erreur.`,'SECRETARY',null,{category:c.category,counterfactual_id:row.id,brier_score:c.brier_score,ex_ante_assessment:c.quality_assessment});
        }
      }catch(e){this.repo.set('settlement_error:'+id,{at:now(),code:this.errorCode(e)});}
    }
    this.repo.set('settlement_cursor',cursor+10>=backlog.length?0:cursor+10);
    const s=this.repo.state()!;s.last_cycle=now();this.repo.save(s);
    if(Date.now()>=Date.parse(s.end_at!))this.finish();
  }
  finish(){
    const s=this.repo.state()!;if(!s.end_at||Date.now()<Date.parse(s.end_at))return;
    const pending=this.repo.one("SELECT count(*) AS n FROM positions WHERE status='PENDING'")?.n||0;
    s.status=pending?'CLOSING':'FINISHED';this.repo.save(s);
    if(!pending&&!this.repo.get('final_report')){const report={finished_at:now(),initial_eur:s.initial_eur,final_eur:D(this.repo.cash()).div(s.fx!.usd_per_eur).toFixed(),positions:this.repo.one('SELECT count(*) AS n FROM positions')?.n||0,limitation:'Seven days and a small number of event bets do not establish future profitability.'};this.repo.set('final_report',report);this.repo.event(s.id+':finish','FINISH','Le défi est terminé. Tous les paris du fonds ont un règlement officiel.','SECRETARY',null,report);}
  }
  async notifications(id?:string){
    for(const row of id?this.repo.rows("SELECT * FROM notifications WHERE id=? AND status='PENDING' AND attempt<3",id):this.repo.rows("SELECT * FROM notifications WHERE status='PENDING' AND attempt<3 ORDER BY created_at LIMIT 1")){
      if(!this.env.NTFY_TOPIC)continue;
      const p=JSON.parse(row.payload);this.repo.run('UPDATE notifications SET attempt=attempt+1 WHERE id=?',row.id);
      try{
        const response=await fetch('https://ntfy.sh',{method:'POST',headers:{'Content-Type':'application/json',...(this.env.NTFY_TOKEN?{Authorization:'Bearer '+this.env.NTFY_TOKEN}:{})},body:JSON.stringify({topic:this.env.NTFY_TOPIC,title:p.title,message:p.message,priority:p.priority,click:p.url}),signal:AbortSignal.timeout(25000)});
        await response.text();if(!response.ok)throw Error('HTTP_'+response.status);this.repo.run("UPDATE notifications SET status='SENT',error=NULL WHERE id=?",row.id);
      }catch(e){this.repo.run('UPDATE notifications SET error=? WHERE id=?',this.errorCode(e),row.id);if(id)throw Error('NOTIFICATION_UNAVAILABLE');}
    }
  }
  summary(){
    const s=this.repo.state()!;const fx=s.fx?.usd_per_eur||'1',cash=this.repo.cash();
    const positions=this.repo.rows('SELECT * FROM positions ORDER BY created_at DESC').map(p=>({...p,payload:JSON.parse(p.payload)}));
    const calls=this.repo.rows("SELECT actor,status,input_tokens,output_tokens,cached_tokens,cache_write_tokens,estimated_eur FROM calls WHERE id NOT LIKE '%:result'");
    const cost=calls.reduce((v,r)=>{if(r.estimated_eur){const e=JSON.parse(r.estimated_eur);v.min=v.min.plus(e.min);v.max=v.max.plus(e.max);}return v;},{min:D(0),max:D(0)});
    const events=this.repo.one('SELECT max(seq) AS seq FROM events')?.seq||0;
    const meetings=this.repo.rows('SELECT * FROM meetings ORDER BY created_at DESC LIMIT 50').map(m=>({...m,payload:JSON.parse(m.payload)}));
    const committed=positions.filter(p=>p.status==='PENDING').reduce((n,p)=>n.plus(p.cost),D(0));
    const profit=positions.filter(p=>p.status==='SETTLED').reduce((n,p)=>n.plus(p.payload.profit),D(0));
    return {state:s,config:CONFIG,members:MEMBERS,cash_quote:cash,cash_eur:D(cash).div(fx).toFixed(),committed_eur:committed.div(fx).toFixed(),profit_eur:profit.div(fx).toFixed(),positions,
      meetings,next_slots:s.started_at?nextSlots(now(),s.end_at,4):[],dossiers:this.repo.rows('SELECT id,market_id,category,status,priority,updated_at,payload FROM dossiers ORDER BY updated_at DESC LIMIT 80').map(d=>({...d,payload:JSON.parse(d.payload),market:this.repo.market(d.market_id)})),
      counterfactuals:this.repo.rows('SELECT * FROM counterfactuals ORDER BY id DESC LIMIT 80').map(c=>({...c,payload:JSON.parse(c.payload)})),
      infrastructure:{azure:{requests:calls.length,failures:calls.filter(c=>!['SUCCESS'].includes(c.status)).length,estimated_eur_min:cost.min.toFixed(),estimated_eur_max:cost.max.toFixed(),invoice_confirmed:false,deployment:this.env.AZURE_DEPLOYMENT,circuit:this.repo.get('azure_circuit')},
        storage_bytes:this.repo.sql.databaseSize??null,notifications_configured:!!this.env.NTFY_TOPIC,notification_failures:this.repo.one("SELECT count(*) AS n FROM notifications WHERE status='PENDING' AND attempt>=3")?.n||0,
        preflight:this.repo.get('preflight'),provider_errors:this.repo.rows("SELECT key,value FROM meta WHERE key LIKE 'provider_error:%'").map(r=>({provider:r.key.split(':')[1],...JSON.parse(r.value)})),scans:Object.fromEntries(CATEGORIES.map(c=>[c,this.repo.get('scan:'+c)])),health:this.repo.get('health'),quota:this.repo.get('quota'),
        jobs:this.repo.rows('SELECT kind,status,count(*) AS count FROM jobs GROUP BY kind,status')},last_event_seq:events,report:this.repo.get('final_report')};
  }
  link(id:string){return this.env.PUBLIC_ORIGIN+'/?phase=3&meeting='+encodeURIComponent(id);}
  errorCode(e:unknown){return e instanceof ProviderError?e.code:e instanceof Error?e.message.slice(0,150):'TECHNICAL_ERROR';}
}
