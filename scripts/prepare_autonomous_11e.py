from pathlib import Path
import sys,json,hashlib,shutil,subprocess,uuid
sys.path.insert(0,'scripts')
from operational_9f_tools import ROOT,checked,inspect,summary,object_inspect,database_snapshot,queue_snapshot
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not Path('phase11e-preflight.json').exists()
for idxname in ['phase11c-evidence-sha256.json']:
 assert all(sha(ROOT/k)==v for k,v in json.loads((ROOT/idxname).read_text()).items())
x=json.loads((ROOT/'phase11d-evidence-index.json').read_text());assert all(sha(ROOT/k)==v for k,v in x['evidence'].items());assert sha(ROOT/'docs/FASE_11D_CONCILIACION_DOCUMENTAL.md')==x['report_sha256']
d=json.loads((ROOT/'phase11d-results.json').read_text());assert all(sha(Path(d['directory'])/'results'/k)==v for k,v in x['logs'].items())
manifest=json.loads((ROOT/'phase11d-source-manifest.json').read_text());assert all(sha(ROOT/'distribution/reconciliation11d'/k)==v for k,v in manifest['files'].items())
b=json.loads((ROOT/'phase11c-build.json').read_text());ctxold=Path(b['context']);assert all(sha(ctxold/k)==v for k,v in json.loads((ROOT/'phase11d-preflight.json').read_text())['candidate_source_hashes'].items())
assert checked(['docker','info','--format','{{.OSType}}']).strip()=='linux'
services={}
ids=checked(['docker','ps','-aq']).splitlines()
for cid in ids:
 raw=inspect(cid);project=raw['Config']['Labels'].get('com.docker.compose.project','')
 if project:services[cid]=summary(raw)
 if project in ['geology-cand11c-858e84aa','geology-local-20261106-57a99a'] and raw['Config']['Labels'].get('com.docker.compose.service') in ['web','worker','servidor','procesador']:
  env=dict(x.split('=',1) for x in raw['Config']['Env'] if '=' in x);assert env['LEVANTAR_AL_CARGAR']=='no';assert all(not v for k,v in env.items() if 'API_KEY' in k or k in ['AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY'])
for k,v in b['images'].items():assert object_inspect('image',b['tags'][k])['Id']==v['id']
original=json.loads((ROOT/'phase11c-original-final.json').read_text());db=database_snapshot();assert db['schema_sha256']==original['database']['schema_sha256'] and db['data_sha256']==original['database']['data_sha256'];assert queue_snapshot()['safe_empty']
backup=Path(json.loads((ROOT/'phase9d-backup-copy.json').read_text())['destination']);back=json.loads((ROOT/'phase9d-final-backup-acl.json').read_text());assert all(sha(backup/f['name'])==f['sha256'] for f in back['files'])
free={k:shutil.disk_usage(k+':/').free for k in ['C','D','F']};assert free['C']>8*1024**3 and free['F']>5*1024**3
base=Path.home()/'GEOLOGY_Autonomous_11E'/('build-'+uuid.uuid4().hex[:10]);base.mkdir(parents=True);ctx=base/'context';shutil.copytree(ctxold,ctx,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for n in ['control','results']:(base/n).mkdir()
sid=checked(['powershell','-NoProfile','-Command','[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value']).strip();checked(['icacls',str(base),'/inheritance:r','/grant:r',f'*{sid}:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'])
source=ROOT/'distribution/reconciliation11d';shutil.copy2(source/'geology/dominio/conciliacion.py',ctx/'geology/dominio/conciliacion.py')
cli=(source/'scripts/reconcile_documents_11d.py').read_text().replace("startswith('geology-recon11d-')","startswith('geology-auto11e-')").replace('isolated 11D only; integration requires approval','isolated 11E certification only')
(ctx/'reconcile_documents.py').write_text(cli,encoding='utf-8',newline='\n')
for n in ['reconciliation_11d_tests.py','reconciliation_redis_outage_11d.py']:
 code=(source/'tests'/n).read_text().replace('geology-recon11d-','geology-auto11e-').replace('/opt/geology-cert/reconcile_documents_11d.py','/opt/geology-distribution/reconcile_documents.py')
 (ctx/'cert'/n).write_text(code,encoding='utf-8',newline='\n')
shutil.copy2(source/'tests/historical-metadata-11d.json',ctx/'cert/historical-metadata-11d.json')
for p in [ctx/'cert/client.py',ctx/'cert/worker.py']:
 p.write_text(p.read_text().replace('geology-cand11c-','geology-auto11e-').replace('geology-auto11a-','geology-auto11e-'),encoding='utf-8',newline='\n')
newdist=ROOT/'distribution/autonomous11e';newdist.mkdir()
for p in (ROOT/'distribution/candidate11c').glob('Dockerfile.*'):shutil.copy2(p,newdist/p.name);shutil.copy2(p,ctx/p.name)
runtime=ctx/'Dockerfile.runtime';text=runtime.read_text().replace('RUN find','COPY --chown=0:0 reconcile_documents.py /opt/geology-distribution/reconcile_documents.py\nRUN chmod 0644 /opt/geology-distribution/reconcile_documents.py \\\n && find');runtime.write_text(text,encoding='utf-8',newline='\n');shutil.copy2(runtime,newdist/runtime.name)
ignore=ctx/'.dockerignore';ignore.write_text(ignore.read_text()+'\n!reconcile_documents.py\n',encoding='utf-8')
oldmanifest=json.loads((ctx/'build-manifest.json').read_text());oldmanifest['source_sha256']={str(p.relative_to(ctx)).replace(chr(92),'/'):sha(p) for p in (ctx/'geology').rglob('*') if p.is_file()};oldmanifest.update(reconciliation_11d_sha256=manifest['files'],operator_cli_sha256=sha(ctx/'reconcile_documents.py'))
(ctx/'build-manifest.json').write_text(json.dumps(oldmanifest,indent=2));shutil.copy2(ctx/'build-manifest.json',newdist/'build-manifest.json')
files=[p for p in ctx.rglob('*') if p.is_file()];assert not any(p.suffix.lower() in ['.pdf','.zip','.dump','.key','.pem','.sql','.xlsx'] or p.name.startswith('.env') for p in files)
pre={'status':'PASS','directory':str(base),'context':str(ctx),'services':json.loads((ROOT/'phase11c-preflight.json').read_text())['services'],'protected_containers':services,'database':db,'documents':original['documents'],'backup_verified':True,'free_bytes':free,'images11c':b['images'],'certified_context_hashes':json.loads((ROOT/'phase11d-preflight.json').read_text())['candidate_source_hashes'],'original_source_hashes':json.loads((ROOT/'phase11c-preflight.json').read_text())['original_source_hashes'],'protected_hashes':json.loads((ROOT/'phase11c-preflight.json').read_text())['protected_hashes']}
(ROOT/'phase11e-preflight.json').write_text(json.dumps(pre,indent=2));print(json.dumps({'preflight':'PASS','directory':str(base),'free_GiB':{k:round(v/1024**3,2) for k,v in free.items()}},indent=2))
