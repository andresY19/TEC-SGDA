"""Restart only the newly created 11A services; preserve all volumes and images."""
from pathlib import Path
import json
import subprocess
import sys

import certify_autonomous_11e as control
ROOT=Path(__file__).resolve().parents[1]

SNAPSHOT=r'''
from pathlib import Path
import os,json,hashlib
from sqlalchemy import text
from geology.nucleo.bd import motor
assert os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-auto11e-')
digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,default=str).encode()).hexdigest()
with motor.connect() as c:
 tables=c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
 data={t:[dict(x) for x in c.execute(text('SELECT * FROM "'+t+'" ORDER BY 1')).mappings()] for t in tables}
 objects=[tuple(x) for x in c.execute(text("SELECT oid,relname,relkind FROM pg_class WHERE relnamespace='public'::regnamespace ORDER BY oid"))]
 constraints=[tuple(x) for x in c.execute(text("SELECT oid,conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY oid"))]
files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for directory in ['/cert/cases','/cert/permissions','/srv/geology/deposito','/srv/geology/expedidos'] for p in Path(directory).rglob('*') if p.is_file()}
print(json.dumps({'tables':len(tables),'row_counts':{k:len(v) for k,v in data.items()},'data_sha256':digest(data),'catalog_sha256':digest([objects,constraints]),'files':files}))
'''

AFTER=r'''
import os,json,unittest,urllib.request,uuid
from pathlib import Path
from geology.nucleo.cola import celery_app
assert os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-auto11e-')
class RestartChecks(unittest.TestCase):
 def test_01_http_after_restart(self):
  op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  for p in ['/estado','/app','/openapi.json']:
   with op.open('http://web:8080'+p,timeout=15) as response:self.assertEqual(response.status,200)
 def test_02_prior_results_persisted(self):
  old=json.loads(Path('/cert/results/operational-certification.json').read_text())['cases']
  for entry in old.values():self.assertEqual(celery_app.AsyncResult(entry['task_id']).state,entry['state'])
  normal=json.loads(Path('/cert/results/normal-runtime.json').read_text())
  for entry in normal.values():self.assertEqual(celery_app.AsyncResult(entry['id']).state,entry['state'])
 def test_03_new_ping_after_restart(self):
  r=celery_app.send_task('geology.ping',task_id=str(uuid.uuid4()),queue=os.environ['GEOLOGY_COLA'])
  self.assertEqual(r.get(timeout=45),'pong')
  with Path('/cert/results/post-restart-ping.json').open('x') as f:json.dump({'task_id':r.id,'state':r.state,'result':'pong'},f)
unittest.main(verbosity=2)
'''


def snapshot():
    r=subprocess.run(['docker','exec','-i',control.cid('runner'),'python','-B','-'],input=SNAPSHOT,capture_output=True,text=True,encoding='utf-8')
    if r.returncode:raise RuntimeError('Temporary snapshot failed')
    return json.loads(r.stdout)


def main():
    state=json.loads((ROOT/'phase11e-environment.json').read_text());control.STATE.update(state)
    assert state['project'].startswith('geology-auto11e-')
    assert state['stage']=='REGRESSION_PASS_PENDING_NORMAL_TASKS_AND_RESTART'
    identities={k:control.cid(k) for k in ['pg','redis','web','worker']}
    for ident in identities.values():
        c=json.loads(control.cmd(['docker','inspect',ident]))[0]
        assert c['Config']['Labels']['com.docker.compose.project']==state['project']
    before=snapshot()
    evidence={'project':state['project'],'before':before,'container_ids':identities,'sequence':[]}
    (ROOT/'phase11e-restart.json').write_text(json.dumps(evidence,indent=2))
    control.compose('stop','worker','web','redis','pg')
    for name in ['pg','redis','web','worker']:
        control.compose('start',name);control.ready(name,name=='worker');evidence['sequence'].append(name)
        assert control.cid(name)==identities[name]
    after=snapshot();assert after==before,'Temporary data/schema/documents changed on restart'
    evidence.update(after=after,persistence_identical=True,containers_recreated=False,ddl_detected=False)
    with (Path(state['directory'])/'results/restart-tests-stdout.txt').open('x') as out, \
         (Path(state['directory'])/'results/restart-tests-stderr.txt').open('x') as err:
        r=subprocess.run(['docker','exec','-i',control.cid('runner'),'python','-B','-'],input=AFTER,text=True,stdout=out,stderr=err,timeout=240)
    evidence['test_returncode']=r.returncode
    (ROOT/'phase11e-restart.json').write_text(json.dumps(evidence,indent=2))
    print((Path(state['directory'])/'results/restart-tests-stderr.txt').read_text()[-2000:])
    assert r.returncode==0
    control.save('CERTIFIED_PENDING_ORIGINAL_FINAL_COMPARISON')


if __name__=='__main__':main()
