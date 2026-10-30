"""Readable, offline HTML and CSV exports from an authentic phase 3 backup."""
import argparse
import csv
from decimal import Decimal as D
import gzip
from html import escape
import json
from pathlib import Path
import re

def load(path):
    p=Path(path)
    return json.loads(gzip.decompress(p.read_bytes()).decode('utf-8') if p.suffix=='.gz' else p.read_text(encoding='utf-8'))
def safe_cell(v):
    text='' if v is None else str(v)
    if text.startswith(('=','+','-','@','\t','\r')) and not re.fullmatch(r'-?\d+(?:\.\d+)?',text):text="'"+text
    return text
def write_csv(path,columns,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f,delimiter=';');writer.writerow(columns)
        for row in rows:writer.writerow([safe_cell(v) for v in row])
def build(backup,output):
    target=Path(output);target.mkdir(parents=True,exist_ok=True)
    meta={r['key']:json.loads(r['value']) for r in backup['meta']};state=meta['state'];fx=D(state.get('fx',{}).get('usd_per_eur','1') if state.get('fx') else '1')
    eur=lambda value: str(D(str(value))/fx)
    money=lambda value:f'{D(str(value)):,.2f} €'.replace(',',' ').replace('.',',')
    positions=[{**r,'payload':json.loads(r['payload'])} for r in backup['positions']]
    meetings=[{**r,'payload':json.loads(r['payload'])} for r in backup['meetings']]
    events=[{**r,'details':json.loads(r['details'])} for r in backup['events']]
    votes=[{**r,'payload':json.loads(r['payload'])} for r in backup['votes']]
    opportunities=[{**r,'payload':json.loads(r['payload'])} for r in backup['counterfactuals']]
    calls=[r for r in backup['calls'] if not r['id'].endswith(':result')]
    write_csv(target/'journal_financier.csv',['Identifiant','UTC','Type','Montant cotation','Equivalent EUR au taux figé','Référence'],[[r['id'],r['at'],r['kind'],r['amount'],eur(r['amount']),r['reference']] for r in backup['ledger']])
    write_csv(target/'paris.csv',['Identifiant','Marché','Question','Domaine','Résultat choisi','Statut','Mise EUR','Quantité','Frais EUR','Paiement EUR','Profit EUR','Probabilité initiale premier outcome','Brier','Justification'],[[p['id'],p['market_id'],p['payload']['question'],p['payload']['category'],p['payload'].get('outcome_label',p['outcome']),p['status'],eur(p['cost']),p['quantity'],eur(p['payload']['fees']),eur(p['payload']['payout']) if p['payload'].get('payout') is not None else None,eur(p['payload']['profit']) if p['payload'].get('profit') is not None else None,p['payload'].get('estimated_yes_probability'),p['payload'].get('brier_score'),p['payload']['reason']] for p in positions])
    write_csv(target/'reunions.csv',['Identifiant','Type','Créneau UTC','Début UTC','Fin UTC','Statut','Compte rendu'],[[m['id'],m['kind'],m['slot'],m['started_at'],m['finished_at'],m['status'],m['payload'].get('summary')] for m in meetings])
    write_csv(target/'votes.csv',['Proposition','Version','Tour','Membre','Vote','Justification','Motif abstention','Condition de réexamen'],[[v['proposal_id'],v['version'],v['round'],v['member_id'],v['payload']['vote'],v['payload']['speech'],v['payload']['abstention_reason'],v['payload']['reconsider_if']] for v in votes])
    write_csv(target/'interventions.csv',['Séquence','UTC','Réunion','Type','Auteur','Texte'],[[e['seq'],e['at'],e['meeting_id'],e['kind'],e['actor'],e['text']] for e in events])
    write_csv(target/'occasions_non_retenues.csv',['Identifiant','Question','Côté','Statut','Motif initial','Date observation UTC','Référence EUR','Profit théorique EUR','Pertinence initiale'],[[o['id'],o['payload']['question'],o['payload']['side'],o['status'],o['payload']['reason'],o['payload'].get('observed_at'),'10',eur(o['payload']['profit']) if o['payload'].get('profit') is not None else None,o['payload'].get('quality_assessment')] for o in opportunities])
    write_csv(target/'consommation_azure.csv',['Identifiant','Auteur','Réunion','UTC','Statut','Jetons entrée','Jetons sortie','Jetons cache','Estimation EUR basse','Estimation EUR haute','Erreur'],[[c['id'],c['actor'],c['meeting_id'],c['created_at'],c['status'],c['input_tokens'],c['output_tokens'],c['cached_tokens'],json.loads(c['estimated_eur'])['min'] if c['estimated_eur'] else None,json.loads(c['estimated_eur'])['max'] if c['estimated_eur'] else None,c['error']] for c in calls])
    cash=sum((D(r['amount']) for r in backup['ledger']),D(0))/fx
    committed=sum((D(p['cost']) for p in positions if p['status']=='PENDING'),D(0))/fx
    profit=sum((D(p['payload']['profit']) for p in positions if p['status']=='SETTLED'),D(0))/fx
    heading='Rapport final' if state['status']=='FINISHED' else 'Rapport intermédiaire'
    if state['status']=='READY':heading='Contrôle de préparation — expérience non lancée'
    if state['mode']!='live':heading='Répétition technique — fonds isolé de la compétition'
    h=escape
    parts=[f'''<!doctype html><html lang="fr"><meta charset="utf-8"><title>PROJECT SURVIVAL — Phase 3</title><style>body{{max-width:1000px;margin:45px auto;padding:0 25px;background:#f4f2ec;color:#1a2929;font:15px/1.7 Arial}}h1,h2{{font-family:Georgia,serif;font-weight:400}}h1{{font-size:40px}}h2{{margin-top:40px;border-bottom:1px solid #cad1c5;padding-bottom:8px}}.label{{font-size:10px;letter-spacing:3px;color:#64735c}}.stats{{display:flex;gap:25px;flex-wrap:wrap}}.stats p{{border:1px solid #c9d0c4;padding:16px;flex:1;min-width:180px}}b{{display:block}}small{{color:#66756d}}article{{padding:12px 0;border-bottom:1px solid #d3d7d0}}article p{{white-space:pre-wrap;margin:5px 0}}details{{margin:15px 0;padding:15px;background:#fff9;border:1px solid #d2d7cc}}summary{{cursor:pointer;font-weight:bold}}table{{width:100%;border-collapse:collapse;font-size:13px}}td,th{{padding:10px;border-bottom:1px solid #d3d7d0;text-align:left}}.warning{{padding:15px;background:#e6e9dd}}@media print{{body{{margin:0;background:white;font-size:11px}}details{{break-inside:avoid}}}}</style><div class="label">PROJECT SURVIVAL · PHASE 03</div><h1>{h(heading)}</h1><p>Expérience : {h(state['id'])}. Export UTC : {h(backup['exported_at'])}.</p><p class="warning">Capital intégralement fictif. Les occasions non retenues n’affectent jamais le fonds. Les performances observées ne prouvent pas une rentabilité future.</p><div class="stats"><p><b>Disponible</b>{money(cash)}</p><p><b>Engagé au coût d’achat</b>{money(committed)}</p><p><b>Résultat officiellement réglé</b>{money(profit)}</p></div>''']
    if not state.get('started_at'):parts.append('<p>Aucun START : le capital prévu n’a pas encore été crédité.</p>')
    if state.get('fx'):parts.append(f"<p>Conversion figée : 1 € = {h(str(fx))} unités de cotation. Référence : {h(state['fx']['reference_date'])}. {h(state['fx']['method'])}.</p>")
    parts.append('<h2>Les investissements</h2>')
    for p in positions:
        r=p['payload'];result=money(D(r['profit'])/fx) if r.get('profit') is not None else 'Règlement officiel en attente'
        parts.append(f"<article><h3>{h(r['question'])}</h3><p>{money(D(p['cost'])/fx)} engagés sur {h(r.get('outcome_label',p['outcome']))}. Résultat : {h(result)}.</p><p>{h(r['reason'])}</p><small>Frais : {money(D(r['fees'])/fx)}. Brier : {h(str(r.get('brier_score') if r.get('brier_score') is not None else 'non calculable'))}.</small></article>")
    if not positions:parts.append('<p>Aucun pari enregistré.</p>')
    parts.append('<h2>Les réunions et les votes</h2><p>Ouvrir une réunion pour lire les interventions réelles. Aucun propos supplémentaire n’est généré par cet export.</p>')
    for meeting in sorted(meetings,key=lambda m:m['created_at']):
        parts.append(f"<details><summary>{h(meeting['started_at'] or meeting['slot'])} — {h(meeting['status'])}</summary><p>{h(meeting['payload'].get('summary',''))}</p>")
        for e in events:
            if e['meeting_id']!=meeting['id'] or e['kind']=='THINKING':continue
            parts.append(f"<article><small>{h(e['at'])} — {h(e['actor'])}</small><p>{h(e['text'])}</p>")
            if e['kind']=='VOTES':
                for v in e['details'].get('votes',[]):parts.append(f"<p><strong>{h(v['member_id'])} : {h({'FOR':'POUR','AGAINST':'CONTRE','ABSTAIN':'ABSTENTION'}[v['vote']])}</strong><br>{h(v['speech'])}</p>")
            parts.append('</article>')
        parts.append('</details>')
    parts.append('<h2>Les décisions non retenues</h2>')
    for o in opportunities:
        r=o['payload'];result=money(D(r['profit'])/fx) if r.get('profit') is not None else 'Gain théorique non calculable ou résultat en attente'
        parts.append(f"<article><b>{h(r['question'])}</b><p>Motif initial : {h(r['reason'])}</p><p>Référence 10 € : {h(result)}.</p><small>{h(r.get('quality_assessment','Non évaluée'))}</small></article>")
    parts.append('<h2>Les preuves et les limites</h2><p>Les sept fichiers CSV joints permettent de vérifier les comptes, votes et consommations. La sauvegarde JSON conserve également les documents et carnets archivés. Les coûts Azure sont des estimations tarifaires sur la consommation connue, pas une facture. Une réponse perdue peut être facturée sans que sa consommation soit connue.</p>')
    if meta.get('final_report'):
        r=meta['final_report'];parts.append(f"<p>Dossiers sérieux examinés : {r.get('serious_dossiers',0)}. Réunions ordinaires terminées : {r.get('meetings',{}).get('completed',0)}. Cycles techniques complets : {r.get('technical_cycles',{}).get('complete',0)}.</p>")
    parts.append('</html>');(target/'rapport.html').write_text(''.join(parts),encoding='utf-8')
    print(json.dumps({'report':str(target/'rapport.html'),'csv_files':7,'mode':state['mode'],'experiment':state['id']}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args();build(load(a.input),a.output)
