from pathlib import Path
import json,hashlib,sys,subprocess
sys.path.insert(0,'scripts');from operational_9f_tools import inspect
ROOT=Path('.').resolve();pre=json.loads((ROOT/'phase11e-preflight.json').read_text());base=Path(pre['directory']);ctx=Path(pre['context'])
p=ctx/'cert/reconciliation_11d_tests.py';p.write_text(p.read_text().replace('/phase11d/historical-metadata-11d.json','/opt/geology-cert/historical-metadata-11d.json').replace('/phase11d/reconcile_documents_11d.py','/opt/geology-distribution/reconcile_documents.py'),encoding='utf-8',newline='\n')
# Freeze a CLI copy for review as well as baking it into the production runtime.
import shutil
shutil.copy2(ctx/'reconcile_documents.py',ROOT/'distribution/autonomous11e/reconcile_documents.py')
# Clone orchestration with all outputs and guards scoped to the NEW environment.
for src,dst in [('certify_candidate_distribution_11c.py','certify_autonomous_11e.py'),('restart_candidate_distribution_11c.py','restart_autonomous_11e.py'),('http_sessions_11c.py','http_sessions_11e.py'),('control_auth_http_11c.py','control_auth_http_11e.py'),('document_security_workflow_11c.py','document_security_workflow_11e.py'),('control_document_security_11c.py','control_document_security_11e.py')]:
 text=(ROOT/'scripts'/src).read_text().replace('certify_candidate_distribution_11c','certify_autonomous_11e').replace('phase11c-','phase11e-').replace('distribution/candidate11c','distribution/autonomous11e').replace('geology-cand11c-','geology-auto11e-').replace('http_sessions_11c','http_sessions_11e').replace('document_security_workflow_11c','document_security_workflow_11e')
 (ROOT/'scripts'/dst).write_text(text,encoding='utf-8',newline='\n')
# Build context contains only allowlisted source and tooling, never live env files.
secrets=[]
for s in pre['protected_containers'].values():
 raw=inspect(s['id']);project=raw['Config']['Labels'].get('com.docker.compose.project','')
 if not project.startswith('geology-'):continue
 env=dict(x.split('=',1) for x in raw['Config']['Env'] if '=' in x)
 secrets += [v.encode() for k,v in env.items() if v and (k in ['PG_CLAVE','GEOLOGY_CLAVE','AWS_SECRET_ACCESS_KEY','POSTGRES_PASSWORD'] or 'API_KEY' in k)]
assert not any(secret in p.read_bytes() for p in ctx.rglob('*') if p.is_file() for secret in secrets)
# Queue-only read on 11C, with credentials retained in container memory.
candidate=[s for s in pre['protected_containers'].values() if inspect(s['id'])['Config']['Labels'].get('com.docker.compose.project')=='geology-cand11c-858e84aa' and inspect(s['id'])['Config']['Labels'].get('com.docker.compose.service')=='web'][0]
code="import redis,os; r=redis.Redis.from_url(os.environ['CELERY_BROKER_URL']);assert not any(r.llen(k) for k in r.scan_iter() if r.type(k)==b'list');assert not any(r.hlen(k) for k in r.scan_iter(match='*unacked*') if r.type(k)==b'hash');r.close();print('candidate queue empty')"
r=subprocess.run(['docker','exec',candidate['id'],'python','-B','-c',code],capture_output=True,text=True);assert r.returncode==0
print('Context secret scan PASS; 11C queue empty; new controllers prepared.')
