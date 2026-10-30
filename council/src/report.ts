import {CONFIG,CATEGORIES,MEMBERS,type State} from './domain';
import {Repository} from './repository';
import {D} from './finance';
import {nextSlots} from './schedule';
export function report(repo:Repository,s:State){
  const fx=s.fx!.usd_per_eur,initial=D(s.initial_eur),cash=D(repo.cash()).div(fx);
  const positions=repo.rows('SELECT * FROM positions ORDER BY created_at').map(p=>({...p,payload:JSON.parse(p.payload)}));
  const meetings=repo.rows('SELECT * FROM meetings').map(m=>({...m,payload:JSON.parse(m.payload)}));
  const ordinary=meetings.filter(m=>m.kind==='ORDINARY'),held=ordinary.filter(m=>m.status==='COMPLETED');
  const expectedMeetings=nextSlots(s.started_at!,s.end_at,40).length;
  const jobs=repo.rows('SELECT id,kind,status FROM jobs'),cycles=new Map<number,Map<string,string>>();
  for(const j of jobs){const match=j.id.match(/^(scan|settle):(\d+)(?::(.+))?$/);if(!match)continue;const bucket=Number(match[2]);if(!cycles.has(bucket))cycles.set(bucket,new Map());cycles.get(bucket)!.set(j.kind==='SETTLE'?'settle':match[3],j.status);}
  const period=CONFIG.scanMinutes*60000,first=Math.floor(Date.parse(s.started_at!)/period),last=Math.floor((Date.parse(s.end_at!)-1)/period);let complete=0,missing=0;
  for(let b=first;b<=last;b++){const statuses=cycles.get(b),expected=b*period<Date.parse(s.betting_deadline!)?['settle',...CATEGORIES]:['settle'];if(expected.every(k=>statuses?.get(k)==='DONE'))complete++;else missing++;}
  let capital=initial,peak=initial,drawdown=D(0);
  for(const p of [...positions].filter(p=>p.status==='SETTLED').sort((a,b)=>a.payload.settled_at.localeCompare(b.payload.settled_at))){capital=capital.plus(D(p.payload.profit).div(fx));if(capital.gt(peak))peak=capital;const currentDrawdown=peak.minus(capital).div(peak);if(currentDrawdown.gt(drawdown))drawdown=currentDrawdown;}
  const categories=CATEGORIES.map(category=>{
    const ps=positions.filter(p=>p.payload.category===category),closed=ps.filter(p=>p.status==='SETTLED'),scored=closed.filter(p=>p.payload.brier_score!==null&&p.payload.brier_score!==undefined);
    return {category,bets:ps.length,settled:closed.length,stake_eur:ps.reduce((n,p)=>n.plus(p.cost),D(0)).div(fx).toFixed(),profit_eur:closed.reduce((n,p)=>n.plus(p.payload.profit),D(0)).div(fx).toFixed(),fees_eur:ps.reduce((n,p)=>n.plus(p.payload.fees),D(0)).div(fx).toFixed(),wins:closed.filter(p=>D(p.payload.profit).gt(0)).length,brier_count:scored.length,brier_mean:scored.length?scored.reduce((n,p)=>n.plus(p.payload.brier_score),D(0)).div(scored.length).toFixed():null};
  });
  const calls=repo.rows("SELECT * FROM calls WHERE id NOT LIKE '%:result' AND created_at>=?",s.started_at!),cost=calls.reduce((n,c)=>{if(c.estimated_eur){const x=JSON.parse(c.estimated_eur);n.min=n.min.plus(x.min);n.max=n.max.plus(x.max);}return n;},{min:D(0),max:D(0)});
  return {experiment_id:s.id,mode:s.mode,started_at:s.started_at,end_at:s.end_at,finished_at:new Date().toISOString(),initial_eur:s.initial_eur,final_eur:cash.toFixed(),profit_eur:cash.minus(initial).toFixed(),roi_percent:cash.minus(initial).div(initial).mul(100).toFixed(),fx:s.fx,
    positions:positions.length,pending_positions:positions.filter(p=>p.status!=='SETTLED').length,max_realized_drawdown_percent:drawdown.mul(100).toFixed(),categories,
    meetings:{expected:expectedMeetings,completed:held.length,no_agenda:ordinary.filter(m=>m.status==='NO_AGENDA').length,cancelled:ordinary.filter(m=>m.status==='CANCELLED').length,completion_percent:expectedMeetings?D(held.length).div(expectedMeetings).mul(100).toFixed():null,within_five_minutes:held.filter(m=>Date.parse(m.started_at)-Date.parse(m.slot)<=300000).length,extraordinary:meetings.filter(m=>m.kind==='EXTRAORDINARY'&&m.status==='COMPLETED').length},
    technical_cycles:{expected:complete+missing,complete,incomplete_or_missing:missing,success_percent:D(complete).div(complete+missing||1).mul(100).toFixed()},
    specialist_participation:MEMBERS.filter(m=>'category' in m).map(m=>({id:m.id,name:m.name,analyses:repo.one("SELECT count(*) n FROM events WHERE actor=? AND kind='ANALYSIS' AND at>=?",m.id,s.started_at)?.n||0})),
    serious_dossiers:repo.one('SELECT count(DISTINCT market_id) n FROM proposals')?.n||0,
    opportunities:repo.rows('SELECT status,count(*) count FROM counterfactuals GROUP BY status'),
    azure:{requests:calls.length,input_tokens:calls.reduce((n,c)=>n+c.input_tokens,0),output_tokens:calls.reduce((n,c)=>n+c.output_tokens,0),successful:calls.filter(c=>c.status==='SUCCESS').length,unknown_cost_calls:calls.filter(c=>c.status==='UNKNOWN').length,estimated_eur_min:cost.min.toFixed(),estimated_eur_max:cost.max.toFixed(),invoice_confirmed:false},
    limitation:'Une semaine et un petit échantillon ne prouvent pas une rentabilité future. Les résultats théoriques des refus ne constituent pas le résultat du fonds. La marge de six heures ne garantit pas le délai de règlement des fournisseurs.'};
}
