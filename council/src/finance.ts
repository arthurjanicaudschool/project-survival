import Decimal from 'decimal.js';
import type {Book, Market, Proposal, Vote, MemberId} from './domain';
Decimal.set({precision:40,rounding:Decimal.ROUND_HALF_UP});
export const D=(x:Decimal.Value)=>new Decimal(x);
export type PaperFill={price:string;quantity:string;fee:string};
export type Execution={status:'FILLED'|'PARTIAL'|'REJECTED';reason:string;fills:PaperFill[];quantity:string;gross:string;fees:string;spent:string};
export function execute(book:Book,budget:string,limit:string,at:string,consumed:Record<string,string>={}):Execution {
  const reject=(reason:string):Execution=>({status:'REJECTED',reason,fills:[],quantity:'0',gross:'0',fees:'0',spent:'0'});
  const age=(Date.parse(at)-Date.parse(book.observed_at))/1000;
  if(!Number.isFinite(age)||age < -5 ||age>180)return reject('STALE_BOOK');
  const rate=D(book.fee_rate),exponent=D(book.fee_exponent),tick=D(book.tick),minimum=D(book.minimum);
  if(rate.lt(0)||rate.gt(1)||exponent.lt(0)||tick.lte(0)||minimum.lte(0))return reject('INVALID_BOOK');
  if(D(budget).lte(0))return reject('ZERO_BUDGET');
  const levels=book.asks.filter(l=>D(l.price).gt(0)&&D(l.price).lt(1)&&D(l.size).gt(0)).sort((a,b)=>D(a.price).cmp(b.price));
  if(!levels.length)return reject('NO_LIQUIDITY');
  const best=D(levels[0].price),priceLimit=D(limit).div(tick).floor().mul(tick),quantum=D('.01');
  const fee=(q:Decimal,p:Decimal)=>q.mul(rate).mul(p.mul(D(1).minus(p)).pow(exponent)).toDecimalPlaces(5,Decimal.ROUND_HALF_UP);
  const unit=(p:Decimal)=>p.plus(rate.mul(p.mul(D(1).minus(p)).pow(exponent)));
  let cap=D(budget).plus('.000005').div(unit(best)).toDecimalPlaces(2,Decimal.ROUND_DOWN);
  if(cap.lt(minimum))return reject('BELOW_MARKET_MINIMUM');
  let remaining=D(budget);const fills:PaperFill[]=[];
  for(const level of levels){
    const price=D(level.price);if(price.gt(priceLimit))break;
    if(!price.mod(tick).eq(0))return reject('INVALID_TICK_IN_BOOK');
    const available=Decimal.max(0,D(level.size).minus(consumed[level.price]||0));
    let q=Decimal.min(available,remaining.plus('.000005').div(unit(price)),cap).toDecimalPlaces(2,Decimal.ROUND_DOWN);
    while(q.gt(0)&&q.mul(price).plus(fee(q,price)).gt(remaining)){
      const excess=q.mul(price).plus(fee(q,price)).minus(remaining);
      q=q.minus(Decimal.max(quantum,excess.div(price).toDecimalPlaces(2,Decimal.ROUND_UP)));
    }
    if(q.lte(0))continue;
    const f=fee(q,price);fills.push({price:price.toFixed(),quantity:q.toFixed(),fee:f.toFixed()});
    remaining=remaining.minus(q.mul(price)).minus(f);cap=cap.minus(q);
    if(remaining.lt('.00001')||cap.eq(0))break;
  }
  if(!fills.length)return reject('PRICE_LIMIT');
  const quantity=fills.reduce((n,f)=>n.plus(f.quantity),D(0)),gross=fills.reduce((n,f)=>n.plus(D(f.quantity).mul(f.price)),D(0)),fees=fills.reduce((n,f)=>n.plus(f.fee),D(0));
  if(gross.plus(fees).gt(budget))throw Error('NEGATIVE_CASH_PREVENTED');
  return {status:remaining.lt('.00001')||cap.eq(0)?'FILLED':'PARTIAL',reason:'',fills,quantity:quantity.toFixed(),gross:gross.toFixed(),fees:fees.toFixed(),spent:gross.plus(fees).toFixed()};
}
export function technicalCheck(p:Proposal,m:Market,cash:string,deadline:string,at:string,invested=false):string|null{
  if(!['YES','NO'].includes(p.side)||typeof p.amount!=='string'||typeof p.max_price!=='string'||!/^(\d+(\.\d+)?|\.\d+)$/.test(p.amount)||!/^(\d+(\.\d+)?|\.\d+)$/.test(p.max_price))return 'INVALID_PROPOSAL';
  if(invested)return 'ALREADY_INVESTED';
  if(!m.active||m.resolved)return 'MARKET_CLOSED';
  if(!m.event_end_at||!Number.isFinite(Date.parse(m.event_end_at)))return 'UNKNOWN_TIMING';
  if(Date.parse(m.event_end_at)>Date.parse(deadline)||Date.parse(m.event_end_at)<=Date.parse(at))return 'OUTSIDE_WINDOW';
  if(D(p.amount).lte(0)||D(p.amount).gt(cash))return 'INSUFFICIENT_CASH';
  if(D(p.max_price).lte(0)||D(p.max_price).gte(1))return 'INVALID_PRICE_LIMIT';
  if(!m.books[p.side])return 'UNKNOWN_FEES';
  return null;
}
export type Tally={decision:'APPROVE'|'REJECT'|'TIE'|'REVIEW_ABSTENTION'|'POSTPONE'|'CANCEL';for:number;against:number;abstain:number;missing:string[];reason:string};
export function tally(expected:MemberId[],votes:Vote[],p:Proposal,reviewed=false):Tally{
  const unique=new Map<string,Vote>();
  for(const v of votes){
    if(!expected.includes(v.member_id)||v.proposal_id!==p.id||v.proposal_version!==p.version)throw Error('VOTE_WRONG_PROPOSAL');
    if(unique.has(v.member_id))throw Error('DUPLICATE_VOTE');
    if(v.vote==='ABSTAIN'&&(v.abstention_reason.trim().length<25||v.reconsider_if.trim().length<15))throw Error('UNJUSTIFIED_ABSTENTION');
    unique.set(v.member_id,v);
  }
  const missing=expected.filter(id=>!unique.has(id)),yes=votes.filter(v=>v.vote==='FOR').length,no=votes.filter(v=>v.vote==='AGAINST').length,abstain=votes.length-yes-no;
  const result=(decision:Tally['decision'],reason:string):Tally=>({decision,for:yes,against:no,abstain,missing,reason});
  if(missing.includes('CHAIR')||missing.length>=2)return result('CANCEL','Président absent ou au moins deux membres indisponibles.');
  if(yes+no<4)return result(!reviewed&&abstain?'REVIEW_ABSTENTION':'POSTPONE','Quatre votes exprimés sont nécessaires.');
  if(yes>=3)return result('APPROVE','Au moins trois voix approuvent la proposition exacte.');
  if(no>=3)return result('REJECT','Au moins trois voix refusent la proposition exacte.');
  if(yes===no)return result(abstain&&!reviewed?'REVIEW_ABSTENTION':'TIE','Égalité après quatre votes exprimés.');
  return result('POSTPONE','Majorité insuffisante.');
}
export function arbitrate(t:Tally,choice:'APPROVE'|'REJECT'|'CANCEL',chairPresent:boolean){
  if(t.decision!=='TIE'||!chairPresent||t.for+t.against<4)throw Error('ARBITRATION_NOT_ALLOWED');
  return choice;
}
