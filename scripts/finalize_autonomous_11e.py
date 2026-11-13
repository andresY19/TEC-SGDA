"""Read-only audit of the new candidate; preserve all prior environments."""
from pathlib import Path
import hashlib,json,re,subprocess,urllib.request
import certify_autonomous_11e as c
from operational_9f_tools import inspect,summary
import restart_autonomous_11e as restart

ROOT=Path(__file__).resolve().parents[1]
def main():
    state=json.loads((ROOT/'phase11e-environment.json').read_text());c.STATE.update(state)
    assert state['project'].startswith('geology-auto11e-')
    assert json.loads((ROOT/'phase11e-document-tests.json').read_text())['returncode']==0
    services={};ids={}
    for name in ['pg','redis','web','worker']:
        raw=inspect(c.cid(name));assert raw['State']['Running'];ids[name]=raw['Id']
        assert raw['Config']['Labels']['com.docker.compose.project']==state['project']
        services[name]=summary(raw)
        if name in ['web','worker']:
            assert raw['Config']['User']=='10001:10001'
            assert raw['HostConfig']['ReadonlyRootfs']
            assert 'ALL' in raw['HostConfig']['CapDrop']
            assert any('no-new-privileges' in x for x in raw['HostConfig']['SecurityOpt'])
            assert not any(m['Destination'].startswith('/srv/geology/geology') for m in raw['Mounts'])
            uid=c.cmd(['docker','exec',raw['Id'],'id']).strip();assert 'uid=10001' in uid and 'gid=10001' in uid
            services[name]['effective_identity']=uid
            env=dict(x.split('=',1) for x in raw['Config']['Env'] if '=' in x)
            assert all(not v for k,v in env.items() if 'API_KEY' in k or k in ['AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY'])
            assert env['LEVANTAR_AL_CARGAR'].lower() in ['no','false','0']
        ports=raw['NetworkSettings']['Ports']
        assert all(not bindings or all(x['HostIp']=='127.0.0.1' for x in bindings) for bindings in ports.values())
    snapshot=restart.snapshot();before=json.loads((ROOT/'phase11e-restart.json').read_text())['before']
    assert snapshot['tables']==27 and snapshot['catalog_sha256']==before['catalog_sha256']
    assert all(snapshot['files'].get(k)==v for k,v in before['files'].items())
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));http={}
    for path in ['/estado','/app','/openapi.json']:
        with opener.open('http://127.0.0.1:'+str(state['port'])+path,timeout=15) as response:http[path]=response.status
        assert http[path]==200
    logrun=subprocess.run(['docker','logs',ids['worker']],capture_output=True,text=True,encoding='utf-8',errors='replace')
    assert logrun.returncode==0
    assert not re.search(r'Task geology\.levantar_hoja\[.*received',logrun.stdout+logrun.stderr)
    audit_code='''
from pathlib import Path
import json,os,redis
from geology.dominio import pdfa_controlado as p
from geology.nucleo.cola import celery_app
from geology.nucleo.bd import SesionLocal
from geology.modelos import Archivo
entries=[]
for root in ['/cert/cases','/srv/geology/deposito']:
 for f in Path(root).rglob('*.json'):
  try:d=json.loads(f.read_text())
  except (ValueError,OSError):continue
  if isinstance(d,dict) and d.get('estado')=='validado_publicado':entries.append(p.verificar_diario(f))
assert entries and {'1b','2b'}<={x['perfil'] for x in entries}
with SesionLocal() as s:
 for a in s.query(Archivo).all():
  for value in [a.ruta,a.ruta_matriz,a.ruta_consulta]:
   if value:assert Path(value).is_file()
r=redis.Redis.from_url(os.environ['AUTH_REDIS_URL'],decode_responses=True)
assert r.config_get('appendonly')['appendonly']=='yes'
assert r.config_get('appendfsync')['appendfsync']=='always'
aof=r.info('persistence');assert aof['aof_enabled']==1 and aof['aof_last_write_status']=='ok'
r.close()
b=redis.Redis.from_url(celery_app.conf.broker_url)
pending={k.decode():b.llen(k) for k in b.scan_iter() if b.type(k)==b'list'}
assert not any(pending.values())
assert not any(b.hlen(k) for k in b.scan_iter(match='*unacked*') if b.type(k)==b'hash')
b.close()
receipts=[]
import hashlib
for root in ['/cert','/srv/geology/deposito']:
 for f in Path(root).rglob('reconciliation-*.json'):
  raw=f.read_bytes();sha=hashlib.sha256(raw).hexdigest();assert f.name=='reconciliation-'+sha+'.json'
  d=json.loads(raw);assert d['state'] in ['RECONCILED','NEEDS_REVIEW'] and not d['automatic_delivery'] and not d['automatic_deletion']
  receipts.append({'path':str(f),'sha256':sha,'state':d['state'],'outcome':d['outcome'],'reason':d['reason']})
assert any(x['reason']=='EXACT_PDFA_SQL_AND_VALIDATION_MATCH' for x in receipts)
doc=json.loads(Path('/srv/geology/expedidos/pruebas_sinteticas_11c/evidence.json').read_text())
print(json.dumps({'journals':entries,'pending':pending,'aof_durable':True,'document_workflow':doc,'reconciliation_receipts':receipts}))
'''
    audit=subprocess.run(['docker','exec','-i',c.cid('runner'),'python','-B','-'],input=audit_code,capture_output=True,text=True,encoding='utf-8')
    assert audit.returncode==0,audit.stderr[-1000:]
    artifact=json.loads(audit.stdout)
    (ROOT/'phase11e-document-audit.json').write_text(json.dumps(artifact,indent=2))
    directory=Path(state['directory'])/'results';counts={}
    expected={'unit-stderr-1.txt':321,'integration-stderr-1.txt':16,'isolated_tools-stderr-1.txt':13,
              'normal-runtime-stderr.txt':6,'restart-tests-stderr.txt':3,'auth-http-stderr.txt':22,
              'durability-stderr.txt':2,'document-security-stderr.txt':20,
              'reconciliation-stderr-1.txt':24,'reconciliation-redis-outage-stderr-1.txt':1,
              'autonomous-reconciliation-stderr.txt':6}
    # Integration runner filenames are recorded by the controller.
    for name,num in expected.items():
        p=directory/name
        if not p.exists() and name=='integration-stderr-1.txt':
            candidates=[x for x in directory.glob('*stderr*') if re.search(r'Ran 16 tests',x.read_text())]
            assert len(candidates)==1;p=candidates[0]
        text=p.read_text();match=re.search(r'Ran (\d+) tests?',text)
        assert match and int(match.group(1))==num,(name,text[-500:])
        assert re.search(r'\nOK\s*$',text) and 'skipped=' not in text
        counts[p.name]=num
    assert sum(counts.values())==434
    out={'status':'PASS','project':state['project'],'services':services,'http':http,
         'database':snapshot,'catalog_unchanged':True,'prior_files_preserved':True,
         'tests':{'reference_passed':428,'new_passed':6,'passed':434,'failed':0,'omitted':0,'blocked':0,'suites':counts},
         'ai_calls':0,'original_data_modified':False,'upgrade_executed':False}
    (ROOT/'phase11e-results.json').write_text(json.dumps(out,indent=2))
    paths=list((ROOT/'distribution/autonomous11e').rglob('*'))+list(ROOT.glob('phase11e-*.json'))+list((ROOT/'scripts').glob('*11e.py'))
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file() and p.name!='phase11e-evidence-sha256.json'}
    (ROOT/'phase11e-evidence-sha256.json').write_text(json.dumps(hashes,indent=2))
    print(json.dumps({'status':'PASS','project':state['project'],'tests':out['tests'],'http':http},indent=2))

if __name__=='__main__':main()
