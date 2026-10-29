import {CONFIG} from './domain';
const formatter=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Paris',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
export function parisParts(date:Date){
  return Object.fromEntries(formatter.formatToParts(date).map(p=>[p.type,p.value]));
}
export function nextSlots(after:string,end?:string|null,count=8):string[]{
  const slots:string[]=[];let t=Math.ceil((Date.parse(after)+1)/3600000)*3600000;
  for(let i=0;i<24*10&&slots.length<count;i++,t+=3600000){
    if(end&&t>Date.parse(end))break;
    const p=parisParts(new Date(t));if(p.minute==='00'&&CONFIG.meetingHours.includes(Number(p.hour)))slots.push(new Date(t).toISOString());
  }
  return slots;
}
export function parisDay(at:string){const p=parisParts(new Date(at));return `${p.year}-${p.month}-${p.day}`;}
export function significantChange(oldPrice:string|undefined,newPrice:string,oldHash:string,newHash:string,lastAt:string,at:string){
  return oldHash!==newHash&&(oldPrice===undefined||Math.abs(Number(oldPrice)-Number(newPrice))>=.04)||Date.parse(at)-Date.parse(lastAt)>=CONFIG.analysisCooldownMinutes*60000;
}
