import {CONFIG,now,type Market,type Category,type Source,type Book} from './domain';
import {Repository} from './repository';
import {D} from './finance';

const GAMMA='https://gamma-api.polymarket.com',CLOB='https://clob.polymarket.com',DATA='https://data-api.polymarket.com';
const allowed=new Set(['gamma-api.polymarket.com','clob.polymarket.com','data-api.polymarket.com','api.frankfurter.dev','api.weather.gov','api.open-meteo.com','site.api.espn.com','api.opendota.com']);
const arr=(x:any):any[]=>Array.isArray(x)?x:typeof x==='string'?JSON.parse(x):[];
const numeric=(v:any)=>v===undefined||v===null?null:D(String(v)).toFixed();
export async function hash(value:unknown){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value))))].map(v=>v.toString(16).padStart(2,'0')).join('');}
export function coveragePreference(m:Market){
  const s=m.url+' '+m.resolution_source;
  return (m.category==='basketball'&&/\/nba-|nba\.com/.test(s)?20:0)+(m.category==='esport'&&/dota/i.test(m.question)?15:0)+(m.category==='tennis'&&/itftennis|challenger|sioux.falls/i.test(s+' '+m.question)?-15:0)+(/player-props|handicap|first-set|game[1-9]|1h-|2h-/.test(s)?-8:0)+Math.log10(Math.max(1,Number(m.liquidity)));
}
export function classify(raw:any):Category|null{
  const s=[raw.question,raw.category,raw.sportsMarketType,...(raw.tags||[]).map((t:any)=>t.slug||t.label),...(raw.events||[]).flatMap((e:any)=>[e.title,e.slug,...(e.tags||[]).map((t:any)=>t.slug||t.label)])].join(' ').toLowerCase();
  if(/highest temperature|lowest temperature|precipitation|rainfall|weather/.test(s))return 'weather';
  if(/counter.strike|league.of.legends|dota|valorant|esport|cs2|\bbo3\b|\bbo5\b/.test(s))return 'esport';
  if(/\bnba\b|\bwnba\b|basketball|euroleague|\bncaab\b/.test(s))return 'basketball';
  if(/\batp\b|\bwta\b|tennis|roland.garros|wimbledon/.test(s))return 'tennis';
  if(/soccer|premier.league|champions.league|bundesliga|ligue.1|la.liga|serie.a|\bmls\b|\bfifa\b/.test(s))return 'football';
  return null;
}
const cities=[
  {names:/atlanta/i,lat:33.6407,lon:-84.4277,tz:'America/New_York',station:'KATL'},
  {names:/new york|nyc/i,lat:40.7769,lon:-73.874,tz:'America/New_York',station:'KLGA'},
  {names:/chicago/i,lat:41.9742,lon:-87.9073,tz:'America/Chicago',station:'KORD'},
  {names:/dallas/i,lat:32.8471,lon:-96.8518,tz:'America/Chicago',station:'KDAL'},
  {names:/miami/i,lat:25.7959,lon:-80.287,tz:'America/New_York',station:'KMIA'},
  {names:/seattle/i,lat:47.4502,lon:-122.3088,tz:'America/Los_Angeles',station:'KSEA'},
  {names:/london/i,lat:51.5053,lon:.0553,tz:'Europe/London',station:'EGLC'},
  {names:/paris/i,lat:48.9694,lon:2.4414,tz:'Europe/Paris',station:'LFPB'},
  {names:/seoul/i,lat:37.4602,lon:126.4407,tz:'Asia/Seoul',station:'RKSI'},
  {names:/tokyo/i,lat:35.5494,lon:139.7798,tz:'Asia/Tokyo',station:'RJTT'},
  {names:/hong kong/i,lat:22.308,lon:113.9185,tz:'Asia/Hong_Kong',station:'VHHH'},
];
export function localMidnight(day:string,tz:string){
  let t=Date.parse(day+'T00:00:00Z');
  for(let i=0;i<3;i++){
    const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(t)).map(x=>[x.type,x.value]));
    const projected=Date.parse(`${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:00Z`);t+=Date.parse(day+'T00:00:00Z')-projected;
  }
  return new Date(t).toISOString();
}
export function timing(raw:any,category:Category):{start:string|null;end:string;method:string}{
  const start=raw.gameStartTime||raw.events?.[0]?.startTime||null;
  let end=raw.endDate||raw.end_date;
  if(!end||!Number.isFinite(Date.parse(end)))throw Error('UNKNOWN_TIMING');
  if(category==='weather'){
    const city=cities.find(c=>c.names.test(raw.question||''));
    const slug=String(raw.events?.[0]?.slug||raw.slug||'');
    const words=slug.match(/(?:on-)?(january|february|march|april|may|june|july|august|september|october|november|december)-(\d{1,2})-(20\d\d)/i);
    const month=words?['january','february','march','april','may','june','july','august','september','october','november','december'].indexOf(words[1].toLowerCase())+1:0;
    const date=slug.match(/(20\d\d-\d\d-\d\d)/)?.[1]||(words?`${words[3]}-${String(month).padStart(2,'0')}-${words[2].padStart(2,'0')}`:null);
    if(!city||!date)throw Error('UNKNOWN_WEATHER_STATION_DAY');
    // The date in Gamma often ends at noon UTC; the observation covers the
    // entire local day. Never mistake the metadata clock for the real event.
    const nextDay=new Date(Date.parse(date+'T12:00:00Z')+86400000).toISOString().slice(0,10);
    return {start:localMidnight(date,city.tz),end:localMidnight(nextDay,city.tz),method:'Complete local calendar day; settlement delay remains possible'};
  }
  if(!start||!Number.isFinite(Date.parse(start)))throw Error('UNKNOWN_SPORT_START');
  const hours=category==='football'?3:category==='basketball'?4:6;
  // Gamma endDate can be the settlement/listing deadline, days after a match.
  // Keep it separately; estimate the event duration from the verified start.
  end=new Date(Date.parse(start)+hours*3600000).toISOString();
  return {start:new Date(start).toISOString(),end,method:`Provider start plus conservative ${hours} hour event envelope; not a resolution guarantee`};
}
export function normalize(raw:any,category:Category,at=now()):Market{
  const outcomes=arr(raw.outcomes),assets=arr(raw.version==='v2'?raw.positionIds:raw.clobTokenIds);
  if(outcomes.length!==2||assets.length!==2)throw Error('BINARY_OUTCOMES_REQUIRED');
  if(raw.version&&!['v1','v2'].includes(raw.version))throw Error('UNKNOWN_PROTOCOL');
  const t=timing(raw,category);
  return {id:String(raw.id),question:raw.question,description:String(raw.description||'').slice(0,14000),category,url:`https://polymarket.com/event/${raw.events?.[0]?.slug||raw.slug}`,group:String(raw.events?.[0]?.id||raw.id),version:raw.version||'v1',
    condition_id:raw.conditionId||null,question_id:raw.questionID||null,assets:{YES:String(assets[0]),NO:String(assets[1])},outcome_labels:{YES:String(outcomes[0]),NO:String(outcomes[1])},start_at:t.start,end_at:raw.endDate,event_end_at:t.end,
    resolution_source:String(raw.resolutionSource||raw.events?.[0]?.resolutionSource||String(raw.description||'').match(/https:\/\/[^\s)]+/)?.[0]||''),active:!!(raw.active&&!raw.closed&&raw.acceptingOrders),resolved:false,payouts:null,resolution_evidence:null,
    liquidity:String(raw.liquidityNum||raw.liquidity||'0'),volume:String(raw.volume24hr||'0'),books:{},delay_seconds:Number(raw.secondsDelay||0),observed_at:at,
    tags:(raw.tags||[]).map((t:any)=>String(t.label||t.slug)),};
}
export function finalResolution(raw:any,rows:any[]):{YES:string;NO:string;evidence:any}|null{
  for(const r of rows){
    if(r.status!=='resolved')continue;
    if(r.conditionId||r.condition_id){if((r.conditionId||r.condition_id)!==raw.conditionId)continue;}
    const payouts=arr(r.payouts),resolvedAt=r.resolvedAt||r.resolved_at;
    if(payouts.length===2&&resolvedAt&&D(payouts[0]).plus(payouts[1]).eq(1)&&payouts.every((x:any)=>D(x).gte(0)&&D(x).lte(1)))return {YES:String(payouts[0]),NO:String(payouts[1]),evidence:{method:'Official final payout vector',resolved_at:resolvedAt}};
    if((raw.version||'v1')==='v1'&&raw.umaResolutionStatus==='resolved'&&(r.transactionHash||r.transaction_hash)){
      const oracle=String(r.price),prices=arr(raw.outcomePrices);const values:Record<string,string[]>={'0':['0','1'],'500000000000000000':['0.5','0.5'],'1000000000000000000':['1','0']};
      const v=values[oracle];if(v&&prices.length===2&&D(prices[0]).eq(v[0])&&D(prices[1]).eq(v[1]))return {YES:v[0],NO:v[1],evidence:{method:'Final UMA price corroborated by Gamma outcomes',transaction_hash:r.transactionHash||r.transaction_hash,observed_at:now()}};
    }
  }return null;
}
export class Markets {
  constructor(private repo:Repository,private transport:typeof fetch=(...args)=>fetch(...args)){}
  async get(url:string,cacheSeconds=0):Promise<any>{
    const u=new URL(url);if(!allowed.has(u.hostname)||u.protocol!=='https:'||u.username||u.password)throw Error('PROVIDER_NOT_ALLOWED');
    const research=this.repo.cache<any>('research:'+url);if(research)return research.data;
    if(cacheSeconds){const cached=this.repo.cache(url);if(cached)return cached;}
    for(let a=0;a<2;a++){
      const c=new AbortController(),timer=setTimeout(()=>c.abort(),CONFIG.fetchTimeoutMs);
      try{
        const r=await this.transport(url,{signal:c.signal,redirect:'manual',headers:{Accept:'application/json','User-Agent':'ProjectSurvival/3.0 (https://project-survival.pages.dev)'}});
        if(!r.ok){if((r.status===429||r.status>=500)&&a===0){const wait=Number(r.headers.get('retry-after')||1);if(wait<=5){await new Promise(q=>setTimeout(q,(wait+.2)*1000));continue;}}throw Error('PROVIDER_HTTP_'+r.status);}
        if(Number(r.headers.get('content-length')||0)>8_000_000)throw Error('PROVIDER_RESPONSE_TOO_LARGE');
        const text=await r.text();if(text.length>8_000_000)throw Error('PROVIDER_RESPONSE_TOO_LARGE');
        const data=JSON.parse(text);if(cacheSeconds)this.repo.putCache(url,data,cacheSeconds);return data;
      }finally{clearTimeout(timer);}
    }throw Error('PROVIDER_UNAVAILABLE');
  }
  async fx(){const r=await this.get('https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD',3600);if(!r.rates?.USD||D(r.rates.USD).lte(0)||(Date.now()-Date.parse(r.date))/86400000>5)throw Error('FX_UNAVAILABLE_OR_STALE');return {usd_per_eur:String(r.rates.USD),reference_date:r.date,source:'ECB reference via Frankfurter',method:'Frozen at explicit START; fictional 1 quote unit = 1 reference USD; no FX trading gain'};}
  async catalog(category:Category,deadline:string):Promise<any[]>{
    const slugs:Record<Category,string[]>={weather:['weather','temperature'],football:['soccer'],basketball:['nba','basketball'],tennis:['tennis'],esport:['esports']};
    const ids=[];for(const slug of slugs[category]){try{const tag=await this.get(`${GAMMA}/tags/slug/${slug}`,86400);if(tag.id)ids.push(tag.id);}catch{/* Alternate tag or general discovery below. */}}
    const all:Record<string,any>={};
    for(const tag of ids.length?ids:[null]){
      for(let page=0;page<12;page++){
        const discoveryEnd=category==='weather'?deadline:new Date(Date.parse(deadline)+7*86400000).toISOString();
        const url=new URL(GAMMA+'/events');Object.entries({active:'true',closed:'false',limit:'10',offset:String(page*10),order:'endDate',ascending:'true',end_date_min:now(),end_date_max:discoveryEnd,...(tag?{tag_id:String(tag)}:{})}).forEach(([k,v])=>url.searchParams.set(k,v));
        const res=await this.get(url.href),events=Array.isArray(res)?res:res.data||[];
        for(const event of events)for(const m of event.markets||[]){const raw={...m,events:[event],tags:[...(event.tags||[]),...(m.tags||[])]};if(classify(raw)===category)all[String(m.id)]=raw;}
        if(events.length<10)break;
      }
    }
    return Object.values(all);
  }
  async inspect(id:string,withBooks=true):Promise<Market>{
    const raw=await this.get(`${GAMMA}/markets/${encodeURIComponent(id)}`),category=classify(raw)||this.repo.market(id)?.category;
    if(!category)throw Error('UNSUPPORTED_CATEGORY');
    // Closed market timing is preserved from the originally verified dossier.
    let m:Market;try{m=normalize(raw,category);}catch(e){const saved=this.repo.market(id);if(!saved)throw e;m={...saved,books:{},active:false,observed_at:now()};}
    if(raw.closed||raw.umaResolutionStatus==='resolved'){
      if(m.condition_id||m.question_id){
        const res=await this.get(`${DATA}/v2/resolutions?${m.condition_id?'condition_id='+encodeURIComponent(m.condition_id):'question_id='+encodeURIComponent(m.question_id!)}`);
        const final=finalResolution(raw,Array.isArray(res)?res:res.data||[]);
        if(final){m.resolved=true;m.active=false;m.payouts={YES:final.YES,NO:final.NO};m.resolution_evidence=final.evidence;}
      }
      return m;
    }
    if(withBooks){
      let rate:string,exponent:string;
      if(raw.feesEnabled===false){rate='0';exponent='1';}
      else if(raw.feesEnabled===true&&raw.feeSchedule?.rate!==undefined&&raw.feeSchedule?.exponent!==undefined){rate=String(raw.feeSchedule.rate);exponent=String(raw.feeSchedule.exponent);}
      else throw Error('UNKNOWN_FEES');
      if(D(rate).lt(0)||D(rate).gt(1)||D(exponent).lt(0))throw Error('UNKNOWN_FEES');
      for(const side of ['YES','NO'] as const){
        const b=await this.get(`${CLOB}/book?token_id=${encodeURIComponent(m.assets[side])}`);
        if(!b.timestamp||!b.hash||!b.min_order_size||!b.tick_size)throw Error('INCOMPLETE_ORDER_BOOK');
        const stamp=typeof b.timestamp==='string'&&b.timestamp.includes('T')?new Date(b.timestamp).toISOString():new Date(Number(b.timestamp)).toISOString();
        const map=(levels:any[],desc=false)=>levels.map(l=>({price:String(l.price),size:String(l.size)})).filter(l=>D(l.price).gt(0)&&D(l.price).lt(1)&&D(l.size).gt(0)).sort((a,b)=>D(a.price).cmp(b.price)*(desc?-1:1)).slice(0,60);
        m.books[side]={asset_id:m.assets[side],observed_at:stamp,asks:map(b.asks||[]),bids:map(b.bids||[],true),minimum:String(b.min_order_size),tick:String(b.tick_size),fee_rate:rate,fee_exponent:exponent,evidence:b.hash};
      }
    }
    return m;
  }
  async source(url:string,title:string,provider:string,select:(data:any)=>any):Promise<Source>{
    try{const raw=await this.get(url,900),selected=select(raw);if(!selected||Array.isArray(selected)&&!selected.length)throw Error('NO_MATCHING_DATA');const text=typeof selected==='string'?selected:JSON.stringify(selected);const source:Source={id:await hash({url,text}),url,title,text:text.slice(0,CONFIG.documentChars),fetched_at:this.repo.cache<any>('research:'+url)?.fetched_at||now(),provider,status:'VERIFIED'};this.repo.document(source);return source;}
    catch(e){const code=e instanceof Error?e.message.slice(0,180):'UNAVAILABLE';this.repo.set('provider_error:'+provider,{at:now(),code});return {id:await hash(url),url,title,text:'Source indisponible : '+code,fetched_at:now(),provider,status:'UNAVAILABLE'};}
  }
  async evidence(m:Market):Promise<Source[]>{
    const sources:Source[]=[];
    const rules:Source={id:await hash({id:m.id,rules:m.description}),url:m.url,title:'Règles officielles du marché',text:m.description,fetched_at:now(),status:'VERIFIED',provider:'Polymarket'};this.repo.document(rules);sources.push(rules);
    if(m.category==='weather'){
      const city=cities.find(c=>c.names.test(m.question));if(!city)return sources;
      const url=`https://api.open-meteo.com/v1/forecast?latitude=${city.lat}&longitude=${city.lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=${encodeURIComponent(city.tz)}&forecast_days=8&temperature_unit=${/°F|fahrenheit/i.test(m.question)?'fahrenheit':'celsius'}`;
      sources.push(await this.source(url,`Prévision maillée près de ${city.station} (pas une mesure de station)`,'Open-Meteo',d=>({location:{station_reference:city.station,grid_latitude:d.latitude,grid_longitude:d.longitude,timezone:d.timezone},units:d.daily_units,forecast:d.daily,limitation:'Grid forecast, not official final station observations. No historical error calibration supplied.'})));
      if(city.station.startsWith('K')){
        try{const point=await this.get(`https://api.weather.gov/points/${city.lat},${city.lon}`,86400);if(point.properties?.forecast)sources.push(await this.source(point.properties.forecast,`Prévision officielle NWS près de ${city.station}`,'NWS',d=>({updated:d.properties?.updated,periods:d.properties?.periods?.slice(0,12),limitation:'Forecast, not final observations; station and market rules remain controlling.'})));}catch{/* Grid source is explicitly labelled; no fabricated official forecast. */}
      }
    }else if(m.category==='esport'){
      sources.push(await this.source('https://api.opendota.com/api/teams','Statistiques publiques des équipes Dota 2','OpenDota',d=>d.filter((t:any)=>(m.question.toLowerCase().includes(String(t.name).toLowerCase())&&String(t.name).length>2)).slice(0,8)));
    }else{
      const day=(m.start_at||m.event_end_at).slice(0,10).replace(/-/g,'');
      const leagues=m.category==='football'?['soccer/eng.1','soccer/esp.1','soccer/ger.1','soccer/fra.1','soccer/ita.1','soccer/bra.1','soccer/usa.1','soccer/uefa.champions']:m.category==='basketball'?['basketball/nba','basketball/wnba']:['tennis/atp','tennis/wta'];
      for(const league of leagues){
        const s=await this.source(`https://site.api.espn.com/apis/site/v2/sports/${league}/scoreboard?dates=${day}`,`Rencontres et informations publiques ${league}`,'ESPN',d=>(d.events||[]).map((e:any)=>({name:e.name,date:e.date,status:e.status?.type,competitors:e.competitions?.flatMap((c:any)=>c.competitors?.map((t:any)=>({name:t.team?.displayName||t.athlete?.displayName,record:t.records,homeAway:t.homeAway,rank:t.curatedRank}))),links:e.links?.map((l:any)=>l.href)})).filter((e:any)=>{const tokens=String(e.name).toLowerCase().split(/\W+/).filter((x:string)=>x.length>3);return tokens.some((x:string)=>m.question.toLowerCase().includes(x));}).slice(0,6));
        if(s.status==='VERIFIED')sources.push(s);
      }
    }
    return sources;
  }
}
