"""Generate deterministic independent Decimal reference cases for the edge port."""
from datetime import datetime,timezone
from decimal import Decimal as D
import json
from pathlib import Path
import random
from survival.models import Book,Level
from survival.engine import execute

rng=random.Random(31029)
at=datetime(2026,10,29,tzinfo=timezone.utc)
cases=[]
for i in range(100):
    first=rng.randint(1,92)
    b=Book(asset_id='reference',observed_at=at,bids=[Level(price=D(first-1 or 1)/100,size=D('100'))],asks=[Level(price=D(p)/100,size=D(rng.randint(1,350))) for p in sorted(set([first,min(99,first+2),min(99,first+6)]))],minimum=D(rng.choice([1,5,10])),tick=D('.01'),fee_rate=D(rng.choice(['0','.02','.03','.1'])),fee_exponent=D(rng.choice(['0','1','2'])),evidence='reference-'+str(i))
    budget=D(rng.randint(1,25000))/100
    limit=D(min(99,first+rng.choice([-1,0,3,10])))/100
    e=execute(b,'BUY',budget,at,slippage=D(1),limit_price=limit)
    cases.append({'book':b.model_dump(mode='json'),'budget':str(budget),'limit':str(limit),'at':at.isoformat(),'expected':{'status':e.status,'reason':e.reason,'quantity':str(e.quantity),'gross':str(e.gross),'fees':str(e.fees),'spent':str(e.gross+e.fees),'fills':[f.model_dump(mode='json') for f in e.fills]}})
target=Path(__file__).resolve().parents[1]/'council/test/decimal-parity.json'
target.write_text(json.dumps(cases,indent=2),encoding='utf-8')
print(f'{len(cases)} Decimal reference cases generated')
