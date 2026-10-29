"""Shared free public research, kept separate from the council scheduler.

No orders, wallets, LLM calls or competition start. Sources retain fetch timestamps.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
import httpx
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
def configuration():
    return {**dotenv_values(ROOT/'.env'),**os.environ}
def compact_espn(d):
    def competition(c):
        return {k:c[k] for k in ['id','date','status','competitors','notes'] if k in c}
    def competitor(c):
        return {k:c[k] for k in ['id','type','homeAway','team','athlete','records','curatedRank','statistics','score'] if k in c}
    events=[]
    for e in d.get('events',[]):
        cs=e.get('competitions',[])+[c for g in e.get('groupings',[]) for c in g.get('competitions',[])]
        for c in cs:
            x=competition(c);x['competitors']=[competitor(t) for t in c.get('competitors',[])]
            for t in x['competitors']:
                for key in ['team','athlete']:
                    if key in t:t[key]={k:v for k,v in t[key].items() if k in ['id','displayName','shortDisplayName','fullName','abbreviation']}
            names=[t.get('team',t.get('athlete',{})).get('displayName','') for t in x['competitors']]
            events.append({'id':e.get('id'),'name':' vs '.join(names) or e.get('name'),'date':c.get('date',e.get('date')),'status':c.get('status',e.get('status')),'competitions':[x],'links':e.get('links',[])})
    return {'events':events,'collector_method':'ESPN public scoreboard, compacted without invented values'}
def research():
    cfg=configuration();api=cfg['COUNCIL_API_URL'];headers={'Authorization':'Bearer '+cfg['COUNCIL_ADMIN_TOKEN']}
    health=httpx.get(api+'/api/health',timeout=30).json()
    if health['state']['status'] in ['FINISHED','CLOSING']:
        print(json.dumps({'research':'inactive_experiment'}));return
    previous=health.get('research_collector',{} ) or {}
    if previous.get('at') and (datetime.now(timezone.utc)-datetime.fromisoformat(previous['at'].replace('Z','+00:00'))).total_seconds()<1500:
        print(json.dumps({'research':'recent_shared_feed_reused'}));return
    leagues=['basketball/nba','basketball/wnba','soccer/eng.1','soccer/esp.1','soccer/ger.1','soccer/fra.1','soccer/ita.1','soccer/bra.1','soccer/usa.1','soccer/uefa.champions','tennis/atp','tennis/wta']
    urls=['https://api.opendota.com/api/teams']
    for day in range(-1,8):
        stamp=(datetime.now(timezone.utc)+timedelta(days=day)).strftime('%Y%m%d')
        urls.extend(f'https://site.api.espn.com/apis/site/v2/sports/{league}/scoreboard?dates={stamp}' for league in leagues)
    results=[]
    with httpx.Client(timeout=40,follow_redirects=False) as client:
        def collect(url):
            r=client.get(url,headers={'User-Agent':'ProjectSurvival/3.0 public-research'});r.raise_for_status()
            data=r.json();fetched=datetime.now(timezone.utc).isoformat()
            if 'espn.com' in url:data=compact_espn(data)
            elif isinstance(data,list):data=[{k:t.get(k) for k in ['team_id','name','rating','wins','losses','last_match_time']} for t in data]
            out=client.post(api+'/admin/research',headers=headers,json={'url':url,'data':data,'fetched_at':fetched});out.raise_for_status()
            return {'url':url,'status':'OK','items':len(data.get('events',[])) if isinstance(data,dict) else len(data),'bytes':len(json.dumps(data))}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(collect,url):url for url in urls}
            for f in as_completed(futures):
                try:results.append(f.result())
                except Exception as e:results.append({'url':futures[f],'status':'ERROR','error':type(e).__name__})
    target=ROOT/'exports/phase3/research-latest.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'sources':results},indent=2),encoding='utf-8')
    ok=sum(r['status']=='OK' for r in results);print(json.dumps({'sources_ok':ok,'sources_failed':len(results)-ok,'bytes_sent':sum(r.get('bytes',0) for r in results)}))
    if ok==0:raise RuntimeError('No public research source available')
def notifications():
    cfg=configuration();api=cfg['COUNCIL_API_URL'];headers={'Authorization':'Bearer '+cfg['COUNCIL_ADMIN_TOKEN']}
    with httpx.Client(timeout=30) as client:
        out=client.get(api+'/admin/notification-outbox',headers=headers);out.raise_for_status();b=out.json();sent=0
        for n in b['notifications']:
            r=client.post('https://ntfy.sh',json={'topic':b['topic'],'title':n['title'],'message':n['message'],'priority':n['priority'],'click':n['url']})
            r.raise_for_status();ack=client.post(api+'/admin/notification-ack',headers=headers,json={'id':n['id']});ack.raise_for_status();sent+=1
            time.sleep(.3)
        print(json.dumps({'notifications_sent':sent}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['research','notifications']);a=p.parse_args();globals()[a.command]()
