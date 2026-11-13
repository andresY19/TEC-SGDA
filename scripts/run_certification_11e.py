"""Execute fresh reference suites only in the new 11E project."""
from pathlib import Path
import json,subprocess,time
import certify_autonomous_11e as c
ROOT=Path(__file__).resolve().parents[1]

def load():
 state=json.loads((ROOT/'phase11e-environment.json').read_text());c.STATE.update(state);assert state['project'].startswith('geology-auto11e-');return state

def stream(name,source,timeout=600):
 state=load();out=Path(state['directory'])/'results'
 with (out/(name+'-stdout.txt')).open('x',encoding='utf-8') as stdout,(out/(name+'-stderr.txt')).open('x',encoding='utf-8') as stderr:
  r=subprocess.run(['docker','exec','-i',c.cid('runner'),'python','-B','-'],input=source,text=True,encoding='utf-8',stdout=stdout,stderr=stderr,timeout=timeout)
 print(name,(out/(name+'-stderr.txt')).read_text()[-1000:],flush=True);assert r.returncode==0,name

def child(name):
 r=subprocess.run(['python','-B',str(ROOT/'scripts'/name)]);assert r.returncode==0,name

if __name__=='__main__':
 deadline=time.monotonic()+1200
 while True:
  s=load()
  if s['stage']=='REGRESSION_PASS_PENDING_NORMAL_TASKS_AND_RESTART':break
  assert s['stage']!='STOPPED_FOR_DIAGNOSIS',s.get('error')
  assert time.monotonic()<deadline;time.sleep(2)
 source=(ROOT/'scripts/check_autonomous_runtime_11a.py').read_text().replace('geology-auto11a-','geology-auto11e-')
 stream('normal-runtime',source)
 child('restart_autonomous_11e.py')
 child('control_auth_http_11e.py')
 stream('durability',(ROOT/'scripts/test_session_durability_11b.py').read_text())
 child('control_document_security_11e.py')
 load();c.logged('reconciliation',['/opt/geology-cert/reconciliation_11d_tests.py'])
 c.compose('stop','redis')
 try:c.logged('reconciliation-redis-outage',['/opt/geology-cert/reconciliation_redis_outage_11d.py'])
 finally:c.compose('start','redis');c.ready('redis');c.ready('web');c.ready('worker',True)
 child('integration_autonomous_reconciliation_11e.py')
 c.save('ALL_TESTS_EXECUTED_PENDING_FINAL_AUDIT')
