"""Phase 3 administration. Never starts an experiment implicitly."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]

def configuration():
    return {**dotenv_values(ROOT / '.env'), **os.environ}

def remember(key, value):
    from dotenv import set_key
    set_key(ROOT / '.env', key, value)

def deploy():
    c = configuration()
    for name in ('CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_API_TOKEN', 'AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_API_KEY'):
        if not c.get(name):
            raise RuntimeError(f'Missing configuration: {name}')
    token = c.get('COUNCIL_ADMIN_TOKEN') or secrets.token_urlsafe(40)
    topic = c.get('COUNCIL_NTFY_TOPIC') or 'survival-' + secrets.token_hex(16)
    remember('COUNCIL_ADMIN_TOKEN', token)
    remember('COUNCIL_NTFY_TOPIC', topic)
    env = dict(os.environ, CLOUDFLARE_API_TOKEN=c['CLOUDFLARE_API_TOKEN'], CLOUDFLARE_ACCOUNT_ID=c['CLOUDFLARE_ACCOUNT_ID'], WRANGLER_SEND_METRICS='false')
    exe = ROOT / 'council/node_modules/.bin/wrangler.cmd'
    subprocess.run([str(exe), 'deploy'], cwd=ROOT/'council', env=env, check=True)
    payload = {'AZURE_ENDPOINT': c['AZURE_OPENAI_ENDPOINT'], 'AZURE_KEY': c['AZURE_OPENAI_API_KEY'], 'ADMIN_TOKEN': token, 'NTFY_TOPIC': topic}
    if c.get('COUNCIL_GITHUB_NOTIFIER_TOKEN'):
        payload['GITHUB_NOTIFIER_TOKEN']=c['COUNCIL_GITHUB_NOTIFIER_TOKEN']
    subprocess.run([str(exe), 'secret', 'bulk'], input=json.dumps(payload), text=True, cwd=ROOT/'council', env=env, check=True)
    with httpx.Client(timeout=30) as client:
        r = client.get(f"https://api.cloudflare.com/client/v4/accounts/{c['CLOUDFLARE_ACCOUNT_ID']}/workers/subdomain", headers={'Authorization': 'Bearer '+c['CLOUDFLARE_API_TOKEN']})
        r.raise_for_status()
        sub = r.json()['result']['subdomain']
    url = f'https://project-survival-council.{sub}.workers.dev'
    remember('COUNCIL_API_URL', url)
    print(json.dumps({'api_url':url, 'experiment_started':False}))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['deploy','health','state','preflight','notify-test','export','start','tick','rehearse','restore'])
    p.add_argument('--instance')
    p.add_argument('--confirm')
    p.add_argument('--output')
    p.add_argument('--market')
    p.add_argument('--input')
    a = p.parse_args()
    if a.command == 'deploy':
        deploy();return
    c = configuration()
    path = {'health':'/api/health','state':'/api/state','preflight':'/admin/preflight','notify-test':'/admin/notifications/test','export':'/admin/export','start':'/admin/start','tick':'/admin/tick','rehearse':'/admin/rehearsal','restore':'/admin/restore'}[a.command]
    if a.instance and not path.startswith('/admin/'):
        raise RuntimeError('Use admin export to inspect an isolated instance')
    method = 'GET' if a.command in ['health','state','export'] else 'POST'
    data = {'confirm':a.confirm} if a.command=='start' else {}
    if a.command=='rehearse':
        if not a.instance or not a.instance.startswith('validation-') or not a.market:
            raise RuntimeError('Rehearsal requires --instance validation-... --market genuine-market-id')
        data={'market_id':a.market}
    if a.command=='restore':
        if not a.instance or not a.instance.startswith('recovery-') or not a.input or not a.confirm:
            raise RuntimeError('Restore requires --instance recovery-... --input backup.json --confirm original-experiment-id')
        data={'backup':json.loads(Path(a.input).read_text(encoding='utf-8')),'confirm_id':a.confirm}
    if a.command=='start' and not a.confirm:
        raise RuntimeError('Explicit --confirm experiment-id is required')
    r = httpx.request(method, c['COUNCIL_API_URL']+path, headers={'Authorization':'Bearer '+c['COUNCIL_ADMIN_TOKEN']}, params={'instance':a.instance} if a.instance else {}, json=data if method=='POST' else None, timeout=180)
    r.raise_for_status()
    if a.output:
        target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(r.json(),ensure_ascii=False,indent=2),encoding='utf-8');print(f'Saved: {target}')
    else:
        print(json.dumps(r.json(),ensure_ascii=True,indent=2))

if __name__=='__main__':
    main()
